# EDGE Screener — audit and approval gate

Audit and target design for turning the prototype `screener EDGE layout.html` into a working EDGE Screener on real data
(user brief "EDGE SCREENER — IMPLEMENTATION BRIEF", 2026-10-27). The approval, the user's decisions of 2026-10-28 and the go
are recorded in `EXEC.md`, section EXEC-SCREENER (moved there from `PLAN.md` SCREENER with the go).

- **Status: approved, Phase 1 in execution.** The audit was read-only: it changed no schema, data, Feature 04, Railway
  variable or deployment. On 2026-10-28 the user decided P1, P2, P3 and P12 as recommended, P4 (stale and price-break
  tickers hidden by default, shown with a remark) with its sub-choice A (their values shown with the remark), and P8 (all
  boards for flow), then gave the go for execution phase by phase on dev, with P5-P7, P15-P19 and P21-P23 following the
  recommendations (UNKNOWNS / PRODUCT DECISIONS 13.2). Still open: P13 before Phase 1b; P9, P10 and P20 before Phase 2;
  P11 and P14 (what stays disabled); P24-P34, raised by PAGE LOAD SEQUENCE and MULTI-USER SCALE AND COST (13.3). CHANGES AWAITING APPROVAL lists every
  change with its decision, and NEXT ACTION the order of execution.
- **Evidence base:** code at `main` `010af1e` (merge `9390032`, which added EXEC-BACKTEST-LOAD and EXEC-BACKTEST-SPIN:
  terminal-api `GET /state`, the backtest worker's catalog kept per publication, a shared rack loader with Web Worker
  decoding on the Backtest page, an edge-bff connection pool, CONTRACT.md [D-L3] replaced); the audit first read `9db630b`,
  and statements about the parts that changed were re-checked. The branch `claude/charming-hamilton-faq25e` adds only
  documentation up to `ad7ba34` (ERRORS D22-D30, C09-C11, M255-M261, R41-R43; PLAN SCREENER; FUTURE_PLAN E1-E5) and
  `88d3344` (the go, EXEC-SCREENER), then, from `8a236eb`, the Phase 1 work in progress. Up to `1b6dcc1` that work only adds new files under
  `apps/edge-bff/screener/` (`git diff --name-status 010af1e 1b6dcc1 -- apps .railway`: additions only, checked
  2026-10-28), so the repository citations below hold there too; later Phase 1 commits change existing files, and the
  citations stay at `main` `010af1e`. Decisions are those of 2026-10-28. Live PostgreSQL read through
  pgweb (role `pgweb`, `default_transaction_read_only on`, 30 s statement timeout) on 2026-10-27, 19:10–21:30 UTC, with
  single read-only re-checks on 2026-10-28; the user's uploads `screener EDGE layout.html` (1,717 lines) and
  `Technical_Indicators_53_Frontend_Display_Spec.xlsx` (not committed: user files; neither are extracts or text dumps of
  them).
- **How it was made:** ten independent audits (prototype model, prototype UI, Feature 04, indicator matrix I01–I27 and
  I28–I53, Backtest reuse, flow, fundamentals and universe, EDGE conventions, compute benchmark); adversarial re-checks of the
  four riskiest (Feature 04, both matrix halves, flow), whose corrections override the audits; three independent designs
  (reliability, performance, simplicity) scored by a judge, who chose the reliability design and grafted the best parts of the
  other two. The area reports, the verifications, the three designs and the judge's synthesis are in
  `verification/screener/audit/`; scripts, SQL and outputs in `verification/screener/evidence/` (market-data dumps not
  committed). After the user's answers of 2026-10-28, three sections were added for the new requirements (PAGE LOAD
  SEQUENCE, MULTI-USER SCALE AND COST, FLOW INDICATOR PROPOSALS (PHASE 2)), and the decisions were carried through every
  section.
- **Evidence notation:** `audit/<area>.md` and `audit/verify_<area>.json` are the area reports and their adversarial
  verifications; `evidence/<area>/<file>` are raw scripts, SQL and outputs; all are relative to `verification/screener/`.
  Repository citations are `path:line` at `main` `010af1e`; citations of `EXEC.md` and `ERRORS_AND_SOLUTIONS.md`, which the
  branch changed, are at the branch (`88d3344` or later) or name the entry. A file named as "local, not committed" was read
  during the audit but is not in the repository.
- **Labels:** **FACT** is seen in code, data or a recorded measurement, with its pointer. **INFERENCE** is derived, not
  observed. **PROPOSED** is a design element, built under the go unless marked open. **UNKNOWN** is not established; the
  check that would settle it is named. **DECIDED** is a product decision the user took (`EXEC.md` EXEC-SCREENER), given with
  the user's words in UNKNOWNS / PRODUCT DECISIONS.
- **When this document and the code disagree, the code wins.**

## Approval gate index

| # | Brief item or user requirement | Section |
|---|---|---|
| 1 | Existing architecture | CURRENT VERIFIED STATE |
| 2 | Feature 04 audit | FEATURE 04 AUDIT |
| 3 | Feature 04 actual date/ticker coverage | FEATURE 04 AUDIT (live coverage) |
| 4 | 53-indicator coverage matrix | 53-INDICATOR COVERAGE MATRIX |
| 5 | Backtest calculation reuse matrix | REUSABLE BACKTEST COMPONENTS |
| 6 | Current vs desired data flow | TARGET ARCHITECTURE (data flow) |
| 7 | Recommended target architecture | BEST RECOMMENDATION, TARGET ARCHITECTURE |
| 8 | Exact code files to change | DATABASE / FEATURE CHANGES (files) |
| 9 | Database changes | DATABASE / FEATURE CHANGES |
| 10 | Feature 04 changes | DATABASE / FEATURE CHANGES |
| 11 | Backfill strategy | DATABASE / FEATURE CHANGES |
| 12 | API contracts | API CONTRACT |
| 13 | Frontend integration plan | FRONTEND INTEGRATION |
| 14 | Test plan | TEST PLAN (and TEST EVIDENCE for what was already checked) |
| 15 | Performance benchmark plan | PERFORMANCE BENCHMARK PLAN (and PERFORMANCE EVIDENCE) |
| 16 | Risks and unresolved product decisions | RISKS / TRADE-OFFS, UNKNOWNS / PRODUCT DECISIONS |
| — | The brief's hard constraints and definition of done, each with its enforcing design element and test | CHANGES AWAITING APPROVAL 14.7 |
| R1 | User requirement (2026-10-28): multi-user, scalable and cost-efficient infrastructure | MULTI-USER SCALE AND COST |
| R2 | User requirement (2026-10-28): time until the page shows after the browser opens, following the Terminal and Backtest load sequence | PAGE LOAD SEQUENCE |
| R3 | User requirement (2026-10-28): an onboarding document (how the Screener works; how to add an indicator or a data source) | Written separately; a Phase 1 step (NEXT ACTION 15.2) |
| — | User request (2026-10-28): 10-20 flow screening indicators for Phase 2, with all boards as the default | FLOW INDICATOR PROPOSALS (PHASE 2) |
| — | The decisions taken, the go, and what is still open | UNKNOWNS / PRODUCT DECISIONS 13.2-13.3; NEXT ACTION 15.3 |

The user's fourth requirement of 2026-10-28, at most two agents per workflow, was withdrawn with the go ("Tidak usah pakai
batasan maks 2 agents/ workflow ya", EXEC-SCREENER).

The prototype's UI capabilities are classified one by one in APPENDIX A (already supported / requires integration / requires
calculation / requires new data / requires product decision); none is dropped silently.


## BEST RECOMMENDATION

Labels: **FACT** (cited), **INFERENCE**, **PROPOSED**, **UNKNOWN**. Every point below is argued, with evidence, in TARGET ARCHITECTURE, DATABASE / FEATURE CHANGES and UNKNOWNS / PRODUCT DECISIONS. **DECIDED** marks a product decision the user took on 2026-10-28 (`EXEC.md`, section EXEC-SCREENER). The user gave the "go" the same day, for execution phase by phase on dev; this report is the approval-gate record, updated with those decisions.

**Status: approved, Phase 1 in execution** (FACT, `EXEC.md` EXEC-SCREENER, 2026-10-28: "Status 2026-10-28: dimulai").

How the page loads after the browser opens (the Terminal and Backtest sequence) and how the infrastructure scales for many users at low cost are designed in PAGE LOAD SEQUENCE and MULTI-USER SCALE AND COST; the flow screening indicators the user asked for are proposed in FLOW INDICATOR PROPOSALS (PHASE 2). The onboarding document (the user's requirement 3: how the Screener works and how to add an indicator or a data source) is written separately; the limit of two agents per workflow (requirement 4) was withdrawn by the user with the go.

**Architecture (PROPOSED; the service and its deploy source DECIDED, P3 a).**
- A new private service, `screener-worker` (Node 22, no npm dependency, `sfo`, no database or bucket credentials), deployed from GitHub `main`, computes every screen and every preview on the server.
- It calls the one formula module the Terminal, the Backtest page and the backtest worker already share: `indicators.ts` `F`, through `registry.ts` and `conditions.ts`. FACT: `F` on full history equals the 15 stored Feature 04 columns (max relative difference 1.16e-15 on 828 rows; `audit/benchmark.md` §2f). No formula is written a second time.
- New pure screener code lives in `apps/edge-bff/screener/src/core/`, outside `backtest/src/core`. FACT: `engine_version` hashes every file in `backtest/src/core` and the worker's `src` (`apps/backtest-worker/src/version.ts:18-21`), so the Backtest's result keys and its worker stay byte-identical.
- edge-bff relays the worker under `/api/v1/screener/*` with its session, CSRF and error conventions. The browser renders a Vite sub-app framed at `/screener` and holds no formula code.

**Feature 04 decision (DECIDED, P2 a, 2026-10-28).** The brief's Option C (mixed model) without a runtime Feature 04 read: Feature 04 stays unchanged (no column, VERSION, checkpoint, worker or migration change) and becomes the parity oracle in tests; the defaults live in a Screener snapshot held in memory per publication; custom parameters are computed dynamically. Options A, B and C are evaluated as the brief defines them in DATABASE / FEATURE CHANGES §7.3. Why Feature 04 is not read at runtime (FACT): it fully serves only 9 of the 53 indicators (2 more partly), stores no OHLV, and finishes on a different schedule than the rack. Extending it means every indicator twice (TA-Lib engine plus streaming state) and a VERSION bump that invalidates 6,076 checkpoints (`audit/feature04.md` §11; `audit/verify_feature04.json` F04-17).

**Data path (DECIDED, P1 a, 2026-10-28).** One source: the rack. The existing terminal-publisher run (07:30 and 19:00 WIB) also writes content-addressed cross-sectional files (`v1/xsection/<name>.<sha16>.json.gz`) and indexes them in `state.json`. terminal-api already serves `GET /state` (EXEC-BACKTEST-LOAD, `apps/terminal-api/app/main.py:297-305`); its answer gains one additive field, the `xsection` index. A new `POST /xsection`, reachable only with the gateway proxy key, grants the files. The worker loads about 14 MB of price history per publication (INFERENCE), recomputes the 53 defaults over full history in 8.1-10.2 s on one thread (FACT, wall time; first-repetition CPU 9.6-10.7 s; `audit/benchmark.md` §2d), and serves every screen from memory. The Screener therefore shows exactly the session the Terminal and the Backtest show.

**Phase 1 (dev only; in execution since the go of 2026-10-28).**
- Universe filters on real data: stocks, sector and industry from `IDX_Stock_Universe` (through the publisher's existing reference file), price, ADV20, history length. Stale tickers and tickers with an unadjusted price break are hidden by default and, when the user shows them through the filter, listed with a remark giving the reason; their values stay visible, and the cells whose lookback crosses the ex-date carry the remark too (DECIDED, P4 and P4.1 A; TEMPORARY for price breaks until the D22 fix).
- All 53 indicators at default or custom parameters; VALUE, STATE and EVENT conditions; ALL, ANY and AT LEAST N with one near-miss rule; ranking, sorting, paging, search.
- 8 of the 9 technical presets (Ichimoku waits for a registry release).
- Server-computed ticker preview with real candles, overlays and event markers; "Stock vs IHSG"; CSV export.
- Saved screens, My metrics and one watchlist in two new `edge_bff` tables (one migration; DECIDED, P12 a).
- Phase 1b, Send to Backtest as a page-only import; Phase 2, flow on all boards by default (DECIDED, P8 b), from publisher window files (Feature 06 and a Feature 05 window as designed; FLOW INDICATOR PROPOSALS 16.10 proposes Feature 03 for the long series), with the indicators the user picks from FLOW INDICATOR PROPOSALS (PHASE 2); later phases wait for definitions or data.

**Not built now (PROPOSED).** Fundamentals (none exist; shown disabled with a reason), market cap (EXEC-MCAP waits for "go"), and the Portfolio123-style performance history (no point-in-time universe; relabelled "Stock vs IHSG").

**Decided by the user on 2026-10-28** (UNKNOWNS / PRODUCT DECISIONS 13.2; `EXEC.md` EXEC-SCREENER): P1 (a) the rack as the one data source; P2 (a) Feature 04 unchanged, defaults recomputed in memory per publication; P3 (a) the `screener-worker` service, deployed from GitHub `main`; P12 (a) the `edge_bff` migration for saved screens and one watchlist; P8 (b) all boards as the flow default; P4: stale tickers and tickers with a price-affecting corporate action between `ADJUSTED_HISTORY_BOUNDARY` (2026-09-12) and their last bar (a derived rule; 8 on 2026-10-27) are hidden by default and shown with a remark when the user asks, and P4.1 (A): their values whose lookback crosses the ex-date stay visible with the remark (the report had recommended blanking them). P5-P7, P15-P19 and P21-P23 follow the recommendations. The go: "Arti gas maksudnya tetap jalankan sesuai fase".

**Still open.**
1. Before Phase 1: nothing; Phase 1 has started (EXEC-SCREENER, status 2026-10-28). Raised after the go (UNKNOWNS 13.3): P24, P27, P28 (cached paint, the session helper, page-load targets) and P32-P34 (one replica on dev, fair sharing per owner, per-replica caches), built to their recommendations unless the user decides otherwise; P29 asks who the many users are and how many; P25, P26, P30 and P31 are EDGE-wide items outside the Screener phase.
2. Before Phase 1b: P13 (its recommendation stands until the user confirms it).
3. Before Phase 2: P9 (bandar definitions), P10 (broker lag) and P20 (flow details), decided after the flow indicator proposals (FLOW INDICATOR PROPOSALS (PHASE 2)); plus a second migration (a read grant for the publisher only, on Feature 06 as designed or Feature 03 as FLOW INDICATOR PROPOSALS 16.10 proposes, chosen with the indicators).
4. Confirming what stays disabled: P11 (fundamentals, market cap) and P14 (screen performance history).


## CURRENT VERIFIED STATE

Snapshot: read-only audit of 2026-10-27, about 19:30–20:10 UTC. The repository was read at `3db84ae` and re-checked against `main` `010af1e` (merge `9390032`), which adds EXEC-BACKTEST-LOAD and EXEC-BACKTEST-SPIN: terminal-api `GET /state`, the backtest worker's catalog kept per publication, a shared rack loader, and an edge-bff connection pool (`git diff --stat 9db630b..010af1e`: 45 files). The database was read through pgweb with SELECT and EXPLAIN only. Evidence notation as in the header: `audit/<area>.md` and `audit/verify_<area>.json` (reports and verifications), `evidence/<area>/<file>` (raw outputs), all relative to `verification/screener/`; repository `path:line` citations are at `main` `010af1e`. Where an adversarial verifier corrected an audit claim, the corrected value is used.

Labels: **FACT** (seen in code, data or a recorded measurement), **INFERENCE** (reasoned from facts), **PROPOSED**, **UNKNOWN**.

### 1. Existing architecture (approval item 1)

#### 1.1 Services, regions and data stores

| Component | What it does for the Screener | Deploy and region | Evidence | Label |
|---|---|---|---|---|
| Postgres (market) | Price, Feature 01–06, universe and catalog tables. PostgreSQL 18.6, about 42 GB, `shared_buffers` 128 MB, `work_mem` 4 MB, 4 GB memory limit | `sfo` | `.railway/railway.ts:9-13`; `audit/verify_flow.json` (section 1 confirmation); `evidence/verify_feature04/v30_settings.out` | FACT |
| `idx-price-cron` | Writes `Price_Stock_Indonesia_IDX` (Daily, `is_final`) once a day and opens `Monitoring_Feature04` in the same transaction | cron `0 10 * * *` UTC, `sfo` | `.railway/railway.ts:88-93`; `apps/idx-price-cron/price_update.py:634-673` | FACT |
| `feature-04-worker` | Always-on queue consumer for `Feature_04_Technical_Indicator` (section 03) | GitHub `main`, watches `/apps/feature-04-worker/**` and `/features/feature04/**`, 1 replica, `sfo` | `.railway/railway.ts:162-169` | FACT |
| `stockbit-updater` | Loads broker data, refreshes F02/F03/F05/F06 and the `_INDEX` tables (including `Feature_04_Technical_Indicator_INDEX`). One round per deployment; no schedule | `sfo`, volume `/data` | `apps/stockbit-updater/README.md:8,20-21`; `refresh.py:149-178`; `audit/verify_flow.json` refuted C2 | FACT |
| `terminal-publisher` | Writes published files to the bucket, twice a day (00:00–01:00 and 12:00–13:05 UTC windows per ERRORS M250) | CLI upload, `sfo` | `audit/edge_conventions.md` §6; `ERRORS_AND_SOLUTIONS.md` M250 | FACT |
| Bucket `terminal-display` | Holds the published price, broker and reference files | `sin` | `.railway/railway.ts:23` | FACT |
| `terminal-api` | `/bundle`, `/files`, `/manifest`, `/reference`, `/history`, `/logo`, and `/state` (the publication: `finished_at`, `price_through`, `broker_through`, `broker_behind_sessions`; no file granted, no quota, no audit row); holds the bucket credentials and its own login on schema `terminal`; per-subscriber quotas | CLI upload, `sfo`, public and private (`terminal-api.railway.internal:8080`) | `audit/edge_conventions.md` §6; `apps/terminal-api/app/main.py:297-305`; `bucket.py` `state` | FACT |
| `backtest-worker` | Backtest jobs and signal previews; no database or bucket credentials by design. Keeps its catalog and reference lists per publication: asks `/state` at most every 60 s and rebuilds only when `finished_at` changes | CLI upload, `sfo`, private only | `.railway/railway.ts:175-180`; `apps/backtest-worker/src/terminal.ts:1-3`; `catalog.ts:58-81` (`ByPublication`); `apps/edge-bff/backtest/CONTRACT.md:77-83` [D-L3] | FACT |
| `edge-bff` | EDGE single-page app, `/terminal-app/`, `/backtest-app/`, `/api/v1`, gateway `/api/terminal/v1` | GitHub `main`, root `/apps/edge-bff`, 1 replica, 1 uvicorn worker, `sfo` | `.railway/railway.ts:181-190` | FACT |

Other buckets (`market-sql-datasets`, `market-ai-conversation-outputs`, `market-ai-audit-artifacts`) are in `sjc` and are not on the Screener path (FACT, `.railway/railway.ts:21-24`).

#### 1.2 The shared formula module

- **FACT.** One formula source serves the Terminal chart, the Backtest page and the backtest worker: `apps/edge-bff/terminal/src/calc/indicators.ts` `F`, with 53 keys (I01–I53). Parameters go through `apps/edge-bff/backtest/src/core/registry.ts` `resolveParams`. Condition series come from `core/conditions.ts` `Calc` and `conditionSeries`. These are pure modules with no DOM and no Node API (`registry.ts:1-4`, `conditions.ts:1-10`; `audit/reuse.md` §0, §1.1).
- **FACT.** `F` on full history equals the 15 stored Feature 04 columns on all 844 equity tickers (114,544 rows, 2026-04-01..2026-10-27): same first valid bar, 0 null mismatches, max relative difference 1.25e-15 (adx_14, PSAB 2026-10-07) (`evidence/verify_matrix_a/v_market.txt`). On the 828 rows of 2026-10-27 alone the maximum is 1.16e-15 (`evidence/benchmark/results/f04_parity.json`).
- **FACT.** The worker checks at start-up that `indicators.ts` and `indRegistry.json` hash to the values in `backtest-registry.json`. Any byte change to either file makes it log `registry_mismatch` and exit until the registry is rebuilt and redeployed (`apps/backtest-worker/src/server.ts:349`; `version.ts:37-41`; `build-registry.mjs:25`). `engine_version` hashes every `.ts` and `.json` file in `backtest/src/core` (`version.ts:18-21`).
- **INFERENCE.** Screener-only code must live outside `indicators.ts` and outside `backtest/src/core`, or the Backtest worker needs a coordinated rebuild and redeploy (`audit/verify_matrix_b.json` additional findings).

#### 1.3 The published-file path

`PostgreSQL → terminal-publisher → bucket terminal-display (sin) → terminal-api → backtest-worker, or browser page through the edge-bff gateway`

| Step | Fact | Evidence | Label |
|---|---|---|---|
| Publisher reads | Price per ticker with `timeframe='Daily' AND is_final`; broker rows from F05; reference file `ref/tickers.json.gz` with ticker, name, type, sector, industry from `IDX_Stock_Universe` | `apps/terminal-publisher/publisher.py:55-62, 96, 416-423` | FACT |
| Publisher window | Price is published from the first stored year (2018-01-02 live) | `publisher.py:321-325, 468-479`; `audit/reuse.md` §1.3 | FACT |
| terminal-api `/bundle` | One grant per ticker; each call takes a per-subscriber advisory lock, runs a usage aggregate and writes one `terminal.access_log` row; presigned URL TTL defaults to 120 s | `apps/terminal-api/app/main.py:318-338, 367`; `store.py:60-66`; migration `20261025_100` l.79 | FACT |
| Quotas | Defaults: 60 files/hour, 30 tickers/hour, 150 tickers/day, 300 MB/day. The edge gateway subscriber has a TEMPORARY 1e9 override | migration `20261025_100` l.79-84; `DATABASE_CHANGELOG.md` 2026-10-26 | FACT |
| Live quota rows | Not readable: pgweb has no access to schema `terminal` | `audit/benchmark.md` §4 | UNKNOWN |
| Worker load | `loadMarket` asks `/bundle` once per ticker, then downloads; it re-asks when an answer is older than TTL minus the 60 s HTTP timeout | `apps/backtest-worker/src/load.ts:104-147`; `terminal.ts:463-465` | FACT |
| Browser load | Terminal and Backtest pages call `/bundle` through edge-bff, then presigned GETs. Both use one rack loader: IndexedDB cache `terminal-files`, 50 MB LRU by sha256, and the download retries. Both download and decode files in a Web Worker | `apps/edge-bff/terminal/src/data/rack.ts:15-16, 29` (`CACHE_LIMIT`, `fileCache`; re-exported by `backtest/src/api/cache.ts:6`); `terminal/src/data/worker.ts:8, 30`; `backtest/src/api/load.ts`, `load.worker.ts` | FACT |
| Feature 04 | Not on this path. No runtime reader in Terminal, Backtest or EDGE. Role `terminal_market_reader` has no SELECT on F04 | `evidence/verify_feature04/v10_acl.out`; `audit/feature04.md` §7 | FACT |
| Full-universe size | Price packs rebuilt with the publisher's encoding: 14.2 MB gzip in total, median 17.2 KB, max 42.3 KB. Decoding all 845 takes 2.8–3.3 s wall (2.9–3.4 s CPU) | `evidence/benchmark/results/packsize.json`, `evidence/benchmark/results/decode_packs.txt` | FACT (rebuild) / INFERENCE (equal to published bytes) |
| Full-universe load cost | About 50 s to 2.5 min cold, with 845 to about 1,690 `/bundle` grants and audit rows | `audit/benchmark.md` §4 | INFERENCE |
| Known defect | Files overwritten under the same key during publisher runs give `DATA_INTEGRITY` | `ERRORS_AND_SOLUTIONS.md` M250 (OPEN) | FACT |

#### 1.4 edge-bff: role and limits

- **FACT.** Single-owner model: `EDGE_OWNER`, one login, every owned query filters `owner_key`; there is no users table (`apps/edge-bff/app/config.py:48`; `main.py:247-252`).
- **FACT.** edge-bff's runtime role can read **0 of the 87** public relations (live `has_table_privilege`). It cannot query Price, Feature 04 or Feature 05 (`audit/edge_conventions.md` §1.3; `audit/reuse.md` §3.4 option E).
- **FACT.** Database access goes through a `psycopg_pool.ConnectionPool` (min 1, max 6, `max_idle` 300 s, each connection checked before use, `connect_timeout` 5 s) with `SET LOCAL statement_timeout = '5s'` per transaction; the pool is closed at shutdown (`apps/edge-bff/app/store.py:22-51`; `app/main.py:194-195`; EXEC-BACKTEST-LOAD step 5, edge-bff deployment `2930a8fd` SUCCESS, `RAILWAY_CHANGELOG.md`). The login role's limit is 20 (live `pg_roles.rolconnlimit` for `edge_bff_login`, re-read 2026-10-28), so the pool keeps at most 6 of them.
- **FACT.** Writes need an exact `Origin`, a CSRF header and a body of at most 131,072 bytes. Sub-app CSP is `script-src 'self'` with no inline scripts (`main.py:39-48, 223-257`).
- **FACT.** The terminal gateway forwards only `manifest`, `reference`, `history`, `logo` (GET) and `files`, `bundle` (POST), with an httpx timeout of 30 s; terminal-api's `/state` is not forwarded (`main.py:34-36, 366-388`).
- **FACT.** The Backtest relay awaits on the event loop with timeout `BACKTEST_TIMEOUT_SECONDS` + 30 s and keeps one preview in flight per owner, latest wins (`app/backtest.py:287, 949-1002`).
- **FACT.** No server table for saved screens, watchlists or preferences exists in any schema (`audit/edge_conventions.md` §3.1).
- **FACT.** No CI runs edge-bff, sub-app or Feature 04 tests; the only workflow is `.github/workflows/database-schema-docs.yml`.

#### 1.5 Backtest worker caps

| Limit | Value | Evidence | Label |
|---|---|---|---|
| Stocks per portfolio or preview | 12 (`MAX_PORTFOLIO_TICKERS`; config may only lower it) | `backtest/src/core/engine.ts:151`; `apps/backtest-worker/src/config.ts:77` | FACT |
| Positions | 12 (`MAX_POSITIONS`) | `engine.ts:150` | FACT |
| Broker rows per job or preview | 20,000,000 (dev); F05 holds about 46.2 M rows | `apps/backtest-worker/README.md:219`; `audit/flow.md` §1 | FACT |
| Download bytes per job or preview | 1.5e9 (dev) | `README.md:218` | FACT |
| Timeout | 900 s | `README.md:220` | FACT |
| Enabled conditions per list | 32 | `README.md:221` | FACT |
| Entry window | `window_bars` 1–20, one window for the whole entry | `conditions.ts` `WINDOW_BARS`, `combineEntry` 269-292 | FACT |
| Compute | 2 threads (jobs, previews), one task each; 1 replica; previews queue one at a time | `src/server.ts:108, 197-235` | FACT |
| Caches | Memory 1.5e9 B per thread; disk 1 GiB shared | `README.md:210-211` | FACT |
| Memory | The 12-stock worst case peaked at 1.31 GB on Railway | `README.md:219` | FACT |
| `/v1/signals` answer | Only `entry_signals` and `last_signal` per ticker; no per-condition values | `core/contract.ts:308-313`; `core/signals.ts:242-245` | FACT |

**INFERENCE.** The worker cannot screen about 845 tickers without lifting the 12-stock cap, adding a lane and changing its memory budget, all on the service the Backtest depends on (`audit/reuse.md` §3.2, §7 item 5).

### 2. What the prototype is

| Finding | Evidence | Label |
|---|---|---|
| One standalone vanilla-JS page with no network calls. All data is synthetic: 94 real IDX ticker names (93 in the universe; WIKA is not), 400 weekday sessions ending 2026-10-23 with no holidays, 14 brokers, random fundamentals | prototype lines 559-735; `evidence/html_ui/catalog.json` | FACT |
| The synthetic foreign flow is built from the next 3 sessions' returns, so the flow presets look predictive by construction | prototype line 700 | FACT |
| 115 screenable metrics: 53 registry indicators (`x_*`), 17 legacy Technical, 13 Flow, 32 Fundamental | `evidence/html_ui/catalog.json`; `audit/html_model.md` §0 | FACT |
| 26 presets: Bandarmology 6, Technical 9, Fundamental 8, Combined 3. All use legacy keys; none uses an `x_*` key | prototype 1083-1115; `audit/html_ui.md` §1 item 4 | FACT |
| Each screen is evaluated in the browser over every ticker; at boot `libCounts` evaluates every preset | prototype 1178, 1187, 1713 | FACT |
| Two indicator engines: `XI` (prototype 866-968) for the 53, and a legacy helper set (753-777) for the Technical metrics and every Technical preset | `audit/verify_matrix_a.json` additional findings | FACT |
| `XI` vs `F` (5 tickers, full history, last 250 bars, 1e-9 × scale): 43 equal. Different: KVO (another formula), HV (sample SD, ×1.026), RVOL (excludes the current bar by default), OBV (starts at 0), PSAR (start and reversal). KAMA, Stoch RSI, CCI, CMO and UO differ on flat windows; HMA at custom lengths (round vs floor of √n) | `evidence/html_model/parity_default.tsv`; custom lengths: `audit/html_model.md` §3.2 and `evidence/html_model/parity_custom.tsv` | FACT |
| Further `XI` differences: VWAP returns the price instead of null when period volume is 0 (line 956); %B null where `F` gives 0.5 on residue-width bands; no zero-denominator guard on PVO and NATR. A/D is **not** different | `audit/verify_matrix_b.json` refuted `b-prototype-engine-differs` | FACT |
| Legacy helpers: EMA seeded with the first value, MACD signal over NaN→0, RSI `l‖1e-9`, STOCH warm-up filled with 50, ATR with bar-0 TR = H−L | prototype 753-777 | FACT |
| "Screen Performance History" is not implemented: the code draws only the selected stock vs IHSG, rebased | prototype 1575-1589 | FACT |
| Saved screens, "My metrics", watchlist and theme live in `localStorage` only | prototype 1136, 1150, 1515, 1644-1653 | FACT |
| Send to Backtest targets `backtest.html#import=<base64>`, which EDGE does not read; it maps 13 legacy keys and none of the 53 | prototype 1655-1693; `audit/reuse.md` §0 item 7 | FACT |

### 3. Data availability summary

| Domain | Source | Coverage | Label |
|---|---|---|---|
| Technical (price) | `Price_Stock_Indonesia_IDX` | 1,330,722 rows, all Daily and final, 845 tickers (844 stocks + IHSG), 2018-01-02 → 2026-10-27; 829 tickers on 2026-10-27; volume in shares (Regular board) | FACT (`evidence/benchmark/data/pull_log.json`; `audit/verify_flow.json` C9) |
| Technical (stored) | Feature 04 (equity 2018 → 2026-10-27; bonds from 2016-01-01); Feature 01 (from 2018-01-02, 828 tickers on 2026-10-27) | see section 03 | FACT |
| Flow | `IDX_Broker_Summary`, F02, F03, F05, F06 | 2016-01-04 → 2026-10-27; broker lag 0 sessions now. The lag returns unless stockbit-updater is redeployed with a valid token after each session; the current token expires 2026-10-28 10:53 UTC | FACT (`audit/verify_flow.json` C1, refuted C2) |
| Fundamentals | none | No statement, ratio, market-cap, shares or free-float column anywhere. 0 of 32 prototype metrics available; dividend yield and years of dividends are derivable from `idx_event_annotation` (5,301 DIVIDEND events; 568 of 844 universe stocks); market cap waits for EXEC-MCAP | FACT (`evidence/fundamentals_universe/column_search.txt`, `evidence/fundamentals_universe/corp_action.txt`) |
| Universe, available | `IDX_Stock_Universe` | Sector (12 values incl. `Undefined`), industry (59 incl. `Undefined`), security type, close, ADV (close × volume, or F03/F06 traded value) | FACT |
| Universe, missing | none | Index membership, listing board, special notation, free float, market cap, listing date, foreign ownership. `market_board` is the trading board (Regular/Nego/Tunai), not the listing board | FACT |
| Universe history | `IDX_Stock_Universe_History` | From 2026-09-28 only. Delisted stocks are absent (survivorship) | FACT (`evidence/fundamentals_universe/universe_history.txt`, `evidence/fundamentals_universe/survivorship.txt`) |

### 4. Data problems found

| # | Problem | Evidence | Impact | Recorded | Label |
|---|---|---|---|---|---|
| 1 | `Universe_Equity_Description` has `Sector` and `Industry` swapped: 841 of 844 rows differ from `IDX_Stock_Universe`; the 3 equal rows are `Undefined` in both | `evidence/fundamentals_universe/ued.txt` | The Screener must read classification from `IDX_Stock_Universe` only | ERRORS D23, OPEN (commit `641e55e`) | FACT |
| 2 | PBSA 1:2 split (ex 2026-10-14) not adjusted: close 845 → 384, older rows on the old scale. On 2026-10-27, F04 shows `rsi_14` 22.8, `sma_50` 706.4 against close 302, `bb_lower_20` 85.7. FORU rights issue (ex 2026-09-22): close 2,560 → 176; `bb_lower_20` negative from 2026-09-25 to 2026-10-16 (minimum −2,114 on 2026-10-12); `sma_50` 1,484 against close 94 on 2026-10-27 | `evidence/verify_feature04/v15_foru.out`, `evidence/verify_feature04/v16_splitcheck.out`, `evidence/verify_feature04/v17_split_breaks.out` | Indicator screens list these stocks as oversold or far below their averages. Of 13 STOCK_SPLITs since 2025, only PBSA is unadjusted | PBSA: ERRORS D22, OPEN. FORU: no ERRORS entry at the audit (grep); added to D22 on 2026-10-28 with the derived count of 8 such tickers | FACT |
| 3 | Price history is mixed: back-adjusted before 2026-09-12, raw after. 180–181 tickers have fractional OHLC from the adjustment | `backtest/src/core/engine.ts:157, 532-533`; `audit/verify_matrix_a.json`, `audit/verify_matrix_b.json` additional findings | A later split leaves a level break; fractional history drives running-sum residue on flat windows (section 04) | D22 covers the mechanism | FACT |
| 4 | Stock bars for 2026-09-17 and 2026-09-18 are missing: the price table holds only IHSG on those dates, while `IDX_Broker_Summary` holds about 24.7k rows per day | `evidence/verify_feature04/v21_ihsg_dates.out`, `evidence/verify_feature04/v22_gapdays.out` | F04 and `F` windows treat 2026-09-16 and 2026-09-21 as adjacent bars for 840 stocks; stock-vs-IHSG joins by date or bar offset are off by 2 sessions across that span; broker days without a price bar drop out of Flow | ERRORS M238, OPEN | FACT |
| 5 | 16 stocks have their last bar before 2026-10-27: ADHI 08-21, PPGL 09-04, IPAC 09-10, INPS 09-16, PTPP 10-02, CSMI and XSPI 10-06, IGAR and TFCO 10-15, BIKE 10-19, BSWD and MPRO 10-20, TRUK 10-21, MASB 10-22, MSIN and TGKA 10-26 | `audit/feature04.md` §8; `audit/verify_matrix_a.json` additional findings | "Latest value per ticker" would mix stale values into today's screen; there is no suspension or notation source to explain them | No ERRORS entry (a state of the data, not a defect). Handled by P4, DECIDED 2026-10-28: hidden by default, shown with the remark `STALE` | FACT |
| 6 | Feature 04 heap is sparse: 2,479 MB, 317,373 pages, 4.36 rows/page, against 19.88 rows/page in the same-schema `_INDEX` table. `n_tup_upd` 9,356,027 vs `n_tup_ins` 1,393,549; last autovacuum 2026-10-11 | `evidence/verify_feature04/v02_tables.out`, `evidence/verify_feature04/v27_ext.out` | About 1.93 GB is free space inside pages (`n_dead_tup` only 4,775); multi-day scans read about 4× more pages. The single-date path is slow for another reason: rows are clustered by ticker, so one date's 828 rows sit on about 843 pages | No entry at the audit (grep "4.36", "VACUUM FULL", "pg_repack": 0); recorded 2026-10-28 as ERRORS D28, OPEN, root cause suspected | FACT (density) / INFERENCE (reclaimable size; `pgstattuple` is not installed) |
| 7 | Five tickers trade (F06 Regular rows on 2026-10-27) but are absent from the universe and the price table: AKKU, CRAB, GTBO, TRUE, UNSP | `audit/verify_flow.json` additional findings | A universe driven by `IDX_Stock_Universe` silently excludes them | No entry at the audit; recorded 2026-10-28 as ERRORS D29, OPEN (37 F06 Regular tickers outside the universe, ETFs included) | FACT |


## FEATURE 04 AUDIT

Approval items 2 (Feature 04 audit) and 3 (actual date and ticker coverage). Sources: the audit `audit/feature04.md` and its SQL/outputs in `evidence/feature04/`, corrected by the adversarial check `audit/verify_feature04.json` and its outputs in `evidence/verify_feature04/`. Evidence notation as in the header: `audit/<area>.md` and `audit/verify_<area>.json` (reports and verifications), `evidence/<area>/<file>` (raw outputs), all relative to `verification/screener/`; a bare `qNN` names the query files `evidence/feature04/qNN_*`; repository `path:line` citations are at `main` `010af1e` (no Feature 04 file changed since `3db84ae`). Database time of the reads: 2026-10-27 19:34–19:52 UTC, PostgreSQL 18.6, role `pgweb` (read-only, 30 s timeout).

Labels: **FACT**, **INFERENCE**, **PROPOSED**, **UNKNOWN**. Where the verifier could not confirm a claim, the claim is labelled UNKNOWN with the check that settles it.

### 1. Verdict

| Topic | Finding | Label | Evidence |
|---|---|---|---|
| Health | 868/868 instruments DONE, generation lag 0. 44,268/44,268 column statuses SUCCESS (868 × 51). 6,076 checkpoints (868 × 7). 0 FAILED or BLOCKED queue rows | FACT | `evidence/verify_feature04/v01_health.out`, `evidence/verify_feature04/v03_logs.out` |
| History depth | Equity 2018-01-02 → 2026-10-27, about 8.8 years, not 3. Bonds from 2016-01-01 | FACT | `evidence/verify_feature04/v04_coverage.out` |
| Match with price | All 844 equity tickers equal `Price_Stock_Indonesia_IDX` in row count, first and last date. Bonds 24/24 | FACT | `evidence/verify_feature04/v04_coverage.out`, `evidence/verify_feature04/v25_bonds.out` |
| Default path speed | Latest-date snapshot 1.6–16.7 ms; latest row per ticker 17–89 ms warm; multi-day all-ticker windows 0.8–2.6 s and cache-dependent | FACT; exact cold timings UNKNOWN (cache state not controlled; check: Phase 17 cold runs on the service) | §10 |
| Storage | 4.36 rows/page against 19.88 in the same-schema `_INDEX` table; about 1.93 GB free space inside pages | FACT / INFERENCE | §10 |
| Fit to the 53 indicators | At registry defaults F04 fully serves **9 of 53** and partly serves **2**; 42 are not served | FACT (corrected) | §11 |
| Option A "extend F04" | Possible but heavy: every indicator twice (full engine and streaming state), a version bump invalidates every checkpoint, two maintenance tools abort at IHSG, and at least six writers must change in step. Not taken: the user decided P2 (a) on 2026-10-28, Feature 04 unchanged and used as the parity oracle (UNKNOWNS / PRODUCT DECISIONS) | FACT (code) / INFERENCE (outcome) / DECIDED (P2 a) | §12 |

### 2. Code inventory

| File | Role | Evidence | Label |
|---|---|---|---|
| `features/feature04/engine.py` (386 lines) | Full-history TA-Lib calculation plus availability validator. `VERSION='feature04-v3-smi14-5-5-th40-talib0.6.8-c0.6.4'` (l.21). 57 `COLUMNS` in physical order (l.51); 51 `FEATURE_COLUMNS` | `engine.py:21-59` | FACT |
| `features/feature04/swing.py` (91) | Pine-style SMI 14/5/5 ±40 swing state | file | FACT |
| `features/feature04/incremental.py` (583) | A separate streaming implementation of SMA/BB, EMA, RSI, ATR, ADX, MACD signal and SMI/swing state. `STATE_VERSION='feature04-state-v3'` (l.36) | file | FACT |
| `features/feature04/pipeline.py` (103) | Bounded manual refresh: limits at l.37-41 and l.74, dry-run by default. Has a bond branch that filters `is_final` and `Timeframe '1D'`; only its equity branch lacks those filters | `pipeline.py:37-41, 47-66, 74` (verifier correction) | FACT |
| `features/feature04/backfill.py` (190) | Serial full-history writer: one ticker per transaction, COPY staging, hash-verified, resumable via `feature04_backfill_log`. **Equity only** | `backfill.py:20-29` | FACT |
| `features/feature04/specs.py` (100) | Column formula/usage text for the migration generators; `assert set(specs)==set(COLUMNS)` | `specs.py:99` | FACT |
| `apps/feature-04-worker/worker.py` (832) | Always-on queue consumer and Telegram outbox dispatcher | file | FACT |
| `apps/feature-04-worker/bootstrap_states.py` (178) | Rebuilds checkpoints from full history; shadow check against the full engine | file | FACT |
| Dockerfile | `python:3.12-slim`; copies engine, swing, incremental, worker and bootstrap only | `apps/feature-04-worker/Dockerfile:1-9` | FACT |
| Railway IaC | 1 replica, restart ALWAYS, watch `/apps/feature-04-worker/**` and `/features/feature04/**`: an engine push to `main` redeploys the worker | `.railway/railway.ts:162-169` | FACT |
| Other copies and writers | `apps/stockbit-updater/deploy.sh:13` copies `features/feature04` into its image (IHSG `_INDEX` refresh). Also importing engine/incremental and writing F04 or its checkpoints: `scripts/repair_fixed_income_dates.py` via `run_fixed_income_repair_job.py` (one-shot bond repair: F04 rows, state, queue), `scripts/ihsg_price_release_job.py` (mode `initialize_feature04`), `scripts/initialize_index_feature_sample.py` | `repair_fixed_income_dates.py:31-35, 342-384`; `ihsg_price_release_job.py:10, 39-48`; `initialize_index_feature_sample.py:13-17, 91-98` | FACT; which are deployed today is UNKNOWN (check: the Railway service list and each service's start command against these scripts) |

### 3. Calculation model and versions

**Calculation model (FACT, `engine.py:128-302`).**
- Rows are grouped by (asset_type, ticker, Daily) and sorted by date. Missing dates are never filled: windows count the ticker's own rows (`window_basis=ENTITY_SESSIONS`, migration `20261025_016`).
- An invalid OHLC row, or a missing volume for an ordinary stock, gets NULL features and restarts every history (`_valid`, `_segments`, l.128-151). Bonds and universe indices may have NULL volume (l.134-137).
- SMA, EMA, RSI, ATR, ADX and BBANDS use TA-Lib with defaults. MACD = `ema_12 − ema_26` (both SMA-seeded); the signal is TA-Lib EMA9 over the MACD values from bar 26 onward, not `talib.MACD` (l.257-266).
- Candles: one TA-Lib call per bar over a fixed 15-bar window, so they do not depend on older history (l.100-117, 287-300). `inside_bar` uses strict Decimal comparisons (l.274-280).
- Dependency bundles are retried and withheld as units: MACD (with `ema_12`/`ema_26`), Bollinger, and the 9 SMI/swing columns (l.62-80).
- Every row is checked against warm-up, candle look-back and swing state. An unexpected NULL is a failure; an expected NULL is SUCCESS with `null_reason` (engine `validate_output_availability`; `incremental.py:523-583`).

**Versions.**

| Item | Value | Label | Evidence |
|---|---|---|---|
| Engine version history | `feature04-v1-…` (42 columns) → `v2` (+`adx_14`, `ema_50`, `ema_200`, `inside_bar`) → `v3-smi14-5-5-th40-…` (+9 SMI/swing). `asset_type` (20261011_006) and `close` (20261011_008) were added without a version bump | FACT | `audit/feature04.md` §3 |
| Live rows | Every one of 1,389,238 rows carries the v3 string and timeframe Daily (pg_stats single value plus four chunked counts; an unchunked count timed out) | FACT | `evidence/verify_feature04/v05_versions.out`, `evidence/verify_feature04/v06_versions2.out` |
| State version | `feature04-state-v3` on all 6,076 checkpoints | FACT | `evidence/verify_feature04/v01_health.out` |
| Catalog numbering | `Feature_Catalog` v1 (42) and v2 (46) inactive, **v4 active (57)**, no v3. The catalog label does not match the engine string | FACT | `evidence/verify_feature04/v12_catalogs.out` |

### 4. Queue, state, checkpoints and incremental suffix

| Step | Behaviour | Evidence | Label |
|---|---|---|---|
| Enqueue | Row triggers AFTER INSERT/UPDATE/DELETE on `Price_Stock_Indonesia_IDX` and `Price_Fixed_Income`, for a material change to a final Daily row, call `enqueue_feature04_group`. It skips universe indices, classifies the ticker with `feature04_asset_type()` (raises unless the ticker is in exactly one universe), deletes checkpoints on or after the dirty date, and upserts one queue row keeping `least(dirty_from_date)` | migrations `20261012_003` l.280-312, `20261025_011` l.88-139, `20261011_006` l.32-49; live `evidence/verify_feature04/v23_funcs.out` | FACT |
| Claim | `FOR UPDATE SKIP LOCKED LIMIT 1`, 15-minute lease, at most 5 source attempts, backoff `min(1800, 30 × 2^(attempts−1))` s, poll every 5 s; one replica, serial | `worker.py:37-41, 91-204, 640, 724, 816-828` | FACT (backoff corrected) |
| Suffix | Needs a checkpoint exactly at the last final source date before `dirty_from_date`, with matching `state_version`, `calculation_version` and source-chain SHA; reads at most `correction_lookback_sessions` rows (IDX = 5); keeps lookback + 2 = 7 checkpoints. Otherwise the job ends **`REPAIR_REQUIRED`**, terminal, with no automatic full-history fallback | `worker.py:239-334, 711-715`; `evidence/verify_feature04/v24_sched.out` | FACT |
| Write | Re-checks claim token, generation and revision (stale job logged SUPERSEDED); deletes target rows for vanished source dates; upserts only successful columns with `IS DISTINCT FROM` (unchanged rows keep `calculated_at`); replaces checkpoints; marks the queue DONE | `worker.py:374-413, 571-582` | FACT |
| Column status and failure isolation | Per-column status in `Feature04_Column_Status` (SUCCESS / FAILED + `null_reason`). A failing group is withheld as a unit and retried; on exhaustion it is terminal FAILED. Other columns of the row still commit | `worker.py`; `engine.py:62-80` | FACT |
| Daily cost | Over the last 7 days 4,248 SUCCESS jobs averaged 0.202 s (max 32.9 s), each reading exactly 1 source row | `evidence/verify_feature04/v19_fresh.out` | FACT |

### 5. Backfill, repair, retry, source correction and notification

| Topic | Behaviour | Evidence | Label |
|---|---|---|---|
| Backfill | `backfill.py` (manual): equity only. Its ticker list is every price ticker, IHSG included; with `--write` the IHSG insert trips `stock_feature_index_guard` (23514) and the tool stops at the first failure, after committing the tickers that sort before IHSG. A dry-run does not abort | `backfill.py:146-172`; verifier F04-19 | INFERENCE, supported |
| Bootstrap | `bootstrap_states.py` lists IHSG as equity and raises "Shadow row-count mismatch" even in `--dry-run`; `--ticker X` avoids it. A full re-bootstrap after a version bump therefore needs a per-ticker loop or a code fix | `bootstrap_states.py:72-76, 100-118`; verifier additional findings | FACT |
| Retry | telegram-trigger `/feature04` → `request_feature04_retry` (SECURITY DEFINER), failures only. Since `20261012_004` the dirty date is the oldest of the latest 5 final sessions. Column retries expand to the dependency bundle | `telegram_trigger.py:103-146`; migration `20261012_004` | FACT |
| Repair | Manual: `backfill.py --tickers X --write` (at most 10 tickers per call), then `bootstrap_states.py --ticker X`, then requeue. A new listing needs the same manual initialisation used for IHSG on 2026-10-23 (`ihsg_price_release_job.py initialize_feature04`); there is no automatic path | `audit/feature04.md` §4; `audit/verify_feature04.json` additional findings; `evidence/verify_feature04/v29_listings.out` | FACT |
| Source correction | A correction inside the last 5 sessions is recalculated exactly | worker suffix rule | FACT |
| Older correction | A correction older than 5 sessions, a first price for a new ticker, or re-ingested history deletes every newer checkpoint; the job then ends `REPAIR_REQUIRED`, and a Telegram retry cannot recover it | code path; live log id 10264 `equity/IHSG REPAIR_REQUIRED … before 2018-01-02` (2026-10-23 16:17 UTC) | INFERENCE, supported (log is FACT) |
| Planned 2026-09-17/18 price refill | EXEC.md ~l.7999 item F3 expects F04 to "recalculate through the normal path". It cannot: each inserted row enqueues dirty date 2026-09-17, live checkpoints are 2026-10-15..10-27, and the suffix would be about 28 rows (> 5; 29 for BBRI in the ERRORS D26 re-check). About 840 equity tickers would end `REPAIR_REQUIRED` and need manual repair (recorded 2026-10-28 as ERRORS D26) | `evidence/verify_feature04/v24_sched.out`; worker suffix rule | FACT from code and live state (not executed) |
| Split handling | Prices are split-adjusted only in the fetched tail; stored history is not re-adjusted after a later split (`price_update.py:311`). PBSA (1:2, ex 2026-10-14) and FORU (rights, ex 2026-09-22) show live level breaks in F04 (PBSA `rsi_14` 22.8, `sma_50` 706.4 vs close 302; FORU `bb_lower_20` down to −2,114) | `evidence/verify_feature04/v15_foru.out`, `evidence/verify_feature04/v16_splitcheck.out`, `evidence/verify_feature04/v17_split_breaks.out`; ERRORS D22 | FACT |
| Notification | idx-price-cron opens `Monitoring_Feature04` in the price transaction; a trigger on `Monitoring_Fixed_Income` does so for bonds. `finalize_runs` sets SUCCESS/PARTIAL/FAILED when every ticker is terminal. The outbox waits until the price Telegram message is recorded sent, then POSTs to telegram-monitor | `price_update.py:634-673`; `worker.py:432-473, 735-813` | FACT |

### 6. Equity, bonds and the `_INDEX` table

- **Identity (FACT).** `asset_type` is in the primary key `(ticker, trade_date, timeframe, asset_type)` with `CHECK asset_type IN ('equity','bonds')`. Classification: `IDX_Stock_Universe` → equity, `Universe_Fixed_income` → bonds.
- **Bonds (FACT).** Read `Price_Fixed_Income` where `metric_type='price' AND "Timeframe"='1D' AND is_final`; volume may be NULL. Volume indicators would therefore be NULL for bonds (INFERENCE).
- **IHSG (FACT).** Excluded from the stock table since `20261025_011` (`is_universe_index()`; trigger `stock_feature_index_guard`). IHSG lives in `Feature_04_Technical_Indicator_INDEX`: created `LIKE … INCLUDING ALL` with `CHECK asset_type='index'` (`20261024_010`); 2,127 rows, 2018-01-02 → 2026-10-27, v3, last `calculated_at` 2026-10-27 12:39 UTC (`evidence/verify_feature04/v20_index.out`).
- **IHSG engine copy (FACT).** The `_INDEX` table is rebuilt by the stockbit-updater INDEX refresh, not by the worker: `refresh.py:149-178` → `scripts/backfill_index_features.py:148-158` recalculates IHSG with `engine.calculate` and COPYs `engine.COLUMNS` into a temp table `LIKE …_INDEX` (l.253). The image pins TA-Lib 0.6.8.
- **Calendar mismatch (FACT).** IHSG has 2 dates no equity row has (2026-09-17, 2026-09-18). A "stock vs IHSG" join on F04 by date or bar offset is off by 2 sessions across that span (`evidence/verify_feature04/v21_ihsg_dates.out`).
- **Doc drift (FACT).** The `_INDEX` `Table_Catalog.update_rule` still says "automatic daily routing is not enabled" (`evidence/verify_feature04/v12_catalogs.out`; ERRORS C09, which found that `scripts/backfill_index_features.py` rewrites that text on every run).

### 7. TA-Lib pin and tests

**TA-Lib pin (FACT).**
- `features/feature04/requirements.txt` and `apps/feature-04-worker/requirements.txt` pin `numpy==2.3.5`, `TA-Lib==0.6.8`, `psycopg[binary]==3.2.13`.
- The cp312 manylinux wheel bundles the C library `libta-lib-…so.0.6.4`; no C build step.
- `library_contract()` (`engine.py:83-97`) refuses anything except Python 0.6.8 / C 0.6.4, compatibility 0, unstable period 0. `incremental.py:39-41` calls it at import.
- INFERENCE: a pin drift makes the worker crash-loop at start rather than write different numbers.

**Tests.**

| Item | Fact | Label |
|---|---|---|
| Suites | `features/feature04/tests`: test_engine, test_extensions, test_swing, test_incremental (five-position correction parity against the full engine), test_diagnostics, test_pipeline | FACT |
| Run | 49 passed in 1.81–1.86 s on a scratch copy; `test_repair_job.py` and `test_selected_date_repair.py` excluded (they need a database and `scripts/repair_fixed_income_dates.py`) (`evidence/verify_feature04/pytest_verify.out`) | FACT |
| Environment | Pins match production, but the scratch venv ran Python 3.13 while the image is `python:3.12-slim` | FACT |
| CI | No workflow runs these tests | FACT |
| Recorded parity | 868-instrument incremental/full shadow plus a live re-run with `changed_rows=0` (`verification/feature04/INCREMENTAL_FINALITY.md`); Terminal TS port vs stored F04, 23 tickers, 1,619 tests (`apps/edge-bff/terminal/tests/calc/PARITY.md`) | FACT (docs) |

### 8. Consumers

| Consumer | How it uses F04 | Evidence | Label |
|---|---|---|---|
| AI | `AI_table_catalog` active (stock and `_INDEX`). `AI_column_catalog`: 49 allowed, 8 hidden, on both tables. `AI_calculation_catalog`: 57 ACTIVE on both. Grants to `market_ai_sql_reader` and `market_ai_preview_owner`. Used by orc preview, sandbox `PRICE_TABLES`, Governor provisioning, ai-data-coverage | `evidence/verify_feature04/v10_acl.out`, `evidence/verify_feature04/v12_catalogs.out`; `app/tools/preview.py:49-52`; `service.py:51` | FACT |
| Telegram and price monitoring | telegram-trigger `/feature04`, telegram-monitor, idx-price-cron monitoring | `telegram_trigger.py:103-146`; `telegram_monitor.py:30, 285-335` | FACT |
| INDEX | stockbit-updater → `backfill_index_features.py` | §6 | FACT |
| Terminal, Backtest, EDGE | **No runtime read.** Only the test tool `terminal/tests/calc/tools/fetch_live.py` reads F04. `terminal_market_reader` has no SELECT on F04 | `evidence/verify_feature04/v10_acl.out` | FACT |
| Generated specs | `scripts/terminal_indicator_spec.py` writes INDICATOR_SPEC rows with source FEATURE_04 naming F04 columns | verifier additional findings | FACT |
| Vocabulary | `Feature_Vocabulary` has no F04 rows | `evidence/verify_feature04/v12_catalogs.out` | FACT |

### 9. Live coverage (approval item 3)

**Summary (FACT, `evidence/verify_feature04/v04_coverage.out`, `evidence/verify_feature04/v25_bonds.out`).**

| Asset | Tickers | Rows | First → last | Start 2018-01-02 / earlier / later | End 2026-10-27 / earlier | Rows per ticker min / median / max | < 200 rows | < 750 rows |
|---|---|---|---|---|---|---|---|---|
| equity | 844 | 1,328,595 | 2018-01-02 → 2026-10-27 | 384 / 0 / 460 | 828 / 16 | 74 / 1,802.5 / 2,125 | 10 | 95 |
| bonds | 24 | 60,643 | 2016-01-01 → 2026-10-27 | 0 / 21 / 3 | 11 / 13 (US bonds end 2026-10-26) | 1,012 / 2,635.5 / 2,761 | 0 | 0 |

**Depth against the user's "about three years" expectation.**
- FACT: equity history runs about 8.8 years. 749 of 844 tickers have at least 750 rows (about 3 trading years); 95 have fewer.
- FACT: equity is published and stored from the first price row in 2018, so the Terminal, the Backtest and F04 start on the same bar (`publisher.py:321-325`).
- UNKNOWN: where the three-year expectation comes from. Greps of terminal-publisher, edge-bff terminal and backtest, backtest-worker, `BACKTEST_END_TO_END.md` and the prototype found only `epsG3y` (verifier F04-24).

**First year of equity history (FACT, q04/q06).**

| Year | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|
| Tickers | 497 | 50 | 45 | 48 | 55 | 76 | 40 | 26 | 7 |

No listing-date column exists (UNKNOWN whether later starts are listings). INFERENCE: spot checks match public IPO dates (GOTO 2022-04-11, BUKA 2021-08-06, AMMN 2023-07-07, BREN 2023-10-09). The newest first price row is RANS on 2026-07-10 (FACT, `evidence/verify_feature04/v29_listings.out`).

**Equity rows by year (FACT, q09).**

| Year | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 YTD |
|---|---|---|---|---|---|---|---|---|---|
| Rows | 98,508 | 111,308 | 120,392 | 143,979 | 156,418 | 167,995 | 181,537 | 188,824 | 159,634 |

**Session gaps (FACT, corrected by the verifier, `evidence/verify_feature04/v28_gaps2.out`).** Against the true session calendar (2,127 IHSG dates, which match `IDX_Broker_Summary`): **0 of 844** equity tickers are gap-free; 840 span the 2026-09-17/18 ingestion gap (ERRORS M238); 222 miss more than 5% of sessions; 9 miss more than 50%; 89,968 ticker-sessions are missing in total. The audit's "242 gap-free" was measured against the observed equity calendar, which already lacks those two dates (`evidence/verify_feature04/v08_gaps.out`). F04 rows exist only where the ticker has a price row.

**Stale tickers (FACT).** 16 stocks end before 2026-10-27: ADHI 08-21, PPGL 09-04, IPAC 09-10, INPS 09-16, PTPP 10-02, CSMI and XSPI 10-06, IGAR and TFCO 10-15, BIKE 10-19, BSWD and MPRO 10-20, TRUK 10-21, MASB 10-22, MSIN and TGKA 10-26.

**NULLs on 2026-10-27 (FACT, `evidence/verify_feature04/v07_nulls.out`).** 828 equity rows: 0 NULLs in every indicator, candle and `close` column except `ema_200` (8) and `last_swing_high` (5). `temp_high`/`_bar` NULL on 789 rows and `temp_low`/`_bar` on 468, by design. Bonds (11 rows): only `temp_*` NULL. `Column_Status.null_reason` agrees (`EXPECTED_FORMULA_NULL`).

**Data validity (FACT).** Equity prices have 0 NULL volumes, 0 invalid OHLC and 0 negatives (40 zero-volume bars), so F04's reset rule has not fired mid-history and does not diverge from the TS `def()` segment rule today (`evidence/verify_feature04/v26_invalid.out`). 123,853 bars (9.3%) have H = L.

**Health of control tables (FACT, `evidence/verify_feature04/v01_health.out`, `evidence/verify_feature04/v03_logs.out`, q11-q12).**

| Table | State |
|---|---|
| Queue | 868 DONE, generation lag 0 |
| `Feature04_Column_Status` | 44,268 rows, all SUCCESS |
| Calculation state | 6,076 = 868 × 7, `feature04-state-v3` |
| `Feature04_Calculation_Log` (column `result`) | 11,964 SUCCESS, 1 FAILED (IHSG, id 10264) |
| `Feature04_Notification_Outbox` | 128 SENT |
| Retry requests | 0 rows |
| `Monitoring_Feature04` | 44 SUCCESS, 73 SKIPPED runs |
| `feature04_backfill_log` | 1,689 COMPLETED over 3 runs, 845 tickers (v2 and v3) |
| Freshness | Latest equity finish 10:09:36 UTC, bonds 11:03:44 UTC. Recent DAILY runs took 6.2, 7.4, 4.0, 23.2 and 3.1 minutes after the price run opened at about 10:00 UTC |

### 10. Query plans, latencies and storage density

Indexes: primary key btree `(ticker, trade_date, timeframe, asset_type)` and `Feature_04_Technical_Indicator_trade_date_idx (trade_date)`. Settings: `shared_buffers` 128 MB, `work_mem` 4 MB (FACT, q01, `evidence/verify_feature04/v30_settings.out`).

| Query (EXPLAIN ANALYZE, BUFFERS) | Plan | Measured | Source | Label |
|---|---|---|---|---|
| `SELECT *` on the latest equity date | Bitmap on `trade_date_idx`; 843 heap buffers for 828 rows | 1.6–2.0 ms warm (16.7 ms in a re-run) | `evidence/feature04/q13_plans.out`; `evidence/benchmark/explain/e1_f04.out`; `evidence/verify_feature04/v09_plans.out` | FACT |
| `DISTINCT ON (ticker)` latest row, last 10 days | Bitmap + sort; 835 tickers (828 current + 7 stale) | 17.4–22.0 ms | `evidence/feature04/q13_plans.out`; `evidence/verify_feature04/v09_plans.out` | FACT |
| Same, last 30 days | 7,364 heap blocks for 18,235 rows | 1,785 ms first touch, 89 ms warm | `evidence/benchmark/explain/e1_f04.out` | FACT |
| `LATERAL … ORDER BY trade_date DESC LIMIT 1` per universe ticker | PK backward scan, 845 probes | 65 ms first touch, 27 ms warm | `evidence/benchmark/explain/e1_f04.out` | FACT |
| Latest date, `rsi_14<30 AND close>sma_50`, joined to price | 839 heap blocks, about one row per page | 84.1 ms cold (837 reads) | `evidence/feature04/q23_join_plan.out` | FACT |
| `max(trade_date)` | Index-only backward | 0.07 ms | `evidence/feature04/q13_plans.out` | FACT |
| BBCA, 3 years, `SELECT *` | PK index scan | 17.7 ms (63 reads) | `evidence/feature04/q13_plans.out` | FACT |
| All equity, 90 days, 4–5 columns | Bitmap on PK | 2,579 ms (17,100 reads); 824 ms partly warm (19,600 buffers) in a re-run | `evidence/feature04/q14_plans_wide.out`; `evidence/verify_feature04/v09_plans.out` | FACT; exact cold time UNKNOWN (cache not controlled; check: Phase 17 cold runs) |
| Per-ticker 1-year max/min close | Parallel bitmap on `trade_date_idx` | 2,243 ms (24,321 reads); same on Price 1,649 ms | `evidence/feature04/q14_plans_wide.out` | FACT for the one run; whether it reproduces is UNKNOWN (the verifier did not re-run it; check: run `evidence/feature04/q14_plans_wide.sql` twice) |
| Full-table GROUP BY | — | > 30 s timeout | q08 | FACT |

Governor acceptance for F04 (that document's checks P1–P5, not this report's product decisions) passed after the date index (`DATABASE_INDEX_ACCEPTANCE.md:268-286`, FACT).

**Storage density.**

| Measure | Value | Label | Evidence |
|---|---|---|---|
| Heap | 2,479 MB, 317,373 pages, 4.36 rows/page (4.38 with the live count); recorded 2026-10-28 as ERRORS D28, root cause suspected | FACT | `evidence/verify_feature04/v02_tables.out` |
| Same-schema `_INDEX` | 2,127 rows in 107 pages, 19.88 rows/page | FACT | `evidence/verify_feature04/v02_tables.out` |
| Row width | Sum of `avg_width` 359 B; with header, null bitmap and line pointer about 400 B, so about 20 rows/page when dense | FACT / INFERENCE | `evidence/verify_feature04/v27_ext.out` |
| Churn | `n_tup_upd` 9,356,027 vs `n_tup_ins` 1,393,549, HOT 36,280; `n_dead_tup` 4,775; last autovacuum 2026-10-11, last manual analyze 2026-10-23 | FACT | `evidence/verify_feature04/v03_logs.out` |
| Reclaimable | About 1.93 GB free space inside pages, left by the 2026-10-11 full rewrites (v2, v3, `asset_type`, `close` backfills). Not measurable directly: `pgstattuple` is not installed | INFERENCE, supported | verifier F04-10 |
| Effect | Bloat inflates multi-day scans about 4×. The single-date path is not bloat-bound: rows are clustered by ticker, so one date's rows sit on about one page each; VACUUM FULL or pg_repack would not change that, only CLUSTER by date or a narrow latest-snapshot table would | FACT (layout) / INFERENCE (effect) | `evidence/verify_feature04/v09_plans.out` |
| Reclaim action | VACUUM FULL or pg_repack takes an exclusive lock and needs approval | PROPOSED | — |

### 11. What F04 can serve to the 53 indicators (corrected)

At registry defaults (`evidence/verify_feature04/registry_list.txt`; `evidence/verify_feature04/derive_check.out` on BBCA, PBID, BNBR against TA-Lib 0.6.8):

| Status | Indicators | How | Label |
|---|---|---|---|
| Fully served, stored (5) | I01 sma(20), I06 macd(12/26/9, all 3 outputs), I13 rsi(14), I27 bollinger(20, 2, SMA), I30 atr(14, RMA) | `sma_20`; `macd`, `macd_signal`, `macd_histogram`; `rsi_14`; `bb_upper/middle/lower_20`; `atr_14` | FACT |
| Fully served, derived by exact arithmetic (4) | I28 %B, I29 bandwidth, I31 natr, I32 stddev (population) | `(close−bb_lower_20)/NULLIF(bb_upper_20−bb_lower_20,0)`; `100·(bb_upper_20−bb_lower_20)/NULLIF(bb_middle_20,0)`; `100·atr_14/close`; `(bb_upper_20−bb_middle_20)/2` (rel ≤ 1.2e-14; 1.3e-9 on flat BNBR windows) | FACT |
| Partly served (2) | I07 adx (ADX only; no +DI/−DI); I25 ppo (line only: `100·(ema_12−ema_26)/ema_26`, rel ≤ 2.4e-16; signal and histogram need a recursive EMA) | `adx_14`; `ema_12`, `ema_26` | FACT |
| Not served (42) | all others | — | FACT |
| Custom lengths that happen to be stored | sma length 50 (`sma_50`); ema lengths 12, 26, 50, 200 (`ema_*`), source close only. No SMA 150/200, no EMA 20 (the registry default), no SMA 10 | PARITY I01/I02 diff 0 | FACT |

- **FACT.** These values equal TS `F` and TA-Lib only when computed from the ticker's first price row. From only the last 260 bars, last-bar `ema_200` differs by 0.13–1.35%; from 500 bars, by 0.10–0.19% (`evidence/verify_feature04/derive_check.out`).
- **FACT.** F04 stores only `close` among OHLCV (no open, high, low, volume) and only `source=close`. Prototype metrics that need highs, lows or volume (hi52, lo52, breakout, volume spike, MACD bullish divergence, Supertrend, Ichimoku, Stochastic) need the price table or on-the-fly calculation whatever F04 holds.
- **FACT.** Of the prototype's Technical presets, only "Bollinger Squeeze Breakout" is fully servable from F04 (bandwidth history plus an upper-band cross). Not servable: Minervini, Oversold in Uptrend (SMA 200), Golden Cross (SMA 50/200), Rebound (SMA 10 + volume), 52W Breakout, Supertrend Flip, Ichimoku. The +DI/−DI operators (`plus`, `dixa`) are not servable.

### 12. Option A (extend Feature 04): what it would take

**Per-indicator code (FACT, from code).**
1. `engine.py`: add the column to `INDICATORS`/`EXTENSIONS`, append it at the end of `COLUMNS` (physical order) and to `FEATURE_COLUMNS`, add `REQUIRED_AFTER` and, for multi-output indicators, `dependency_closure`; add a `run_group`; bump `VERSION` (the precedent for every formula column).
2. `incremental.py`: add a streaming state (`new_state`, `_reset_segment` keys, an update function, a group in `calculate_incremental`, a rule in `validate_incremental_availability`); bump `STATE_VERSION`. INFERENCE: this doubles the implementation, and stateful ones are non-trivial (PSAR, SuperTrend, KAMA, TSI, KVO, NVI/PVI, cumulative OBV/ADL/PVT). Volume indicators must be NULL for bonds and IHSG.
3. `specs.py` (assert l.99), the migration generators `scripts/generate_feature04*_migration.py`, `FEATURE04_COLUMN_DEFINITIONS.md`, `FEATURE04_TECHNICAL_INDICATOR.md`, `scripts/terminal_indicator_spec.py` and the PARITY oracle tools.

**Migration (FACT, pattern from `20261011_002`/`003`).**
- Guarded `ALTER TABLE … ADD COLUMN` with CHECK and COMMENT on **both** `Feature_04_Technical_Indicator` and `_INDEX`; without the `_INDEX` column the INDEX refresh COPY fails (`backfill_index_features.py:157, 253`; INFERENCE).
- `CREATE OR REPLACE feature04_output_columns()` (used by retry).
- `Table_Catalog`, `Column_Catalog`; `Feature_Catalog` cut-over (deactivate v4, insert v5) for the main table **and** the `_INDEX` rows (57 active v1 `Feature_Catalog` rows, 57 `AI_calculation_catalog` and 57 `AI_column_catalog` rows for `_INDEX`; `evidence/verify_feature04/v12_catalogs.out`).
- Baseline `Feature04_Column_Status` rows derived from the target (lesson of `20261011_009`); AI catalog rows if exposed; `scripts/audit_feature_catalog_semantics.py` fails if a physical column lacks an active definition.

**Operations, in order (FACT from README and code; outcome INFERENCE).** Pause the worker → migration → full rewrite `backfill.py --all-source-tickers --write` → `bootstrap_states.py` (dry-run, then write) → ANALYZE → redeploy the worker (automatic on `main`) **and** stockbit-updater (manual `deploy.sh`) → refresh `_INDEX`. A `VERSION`/`STATE_VERSION` change makes every checkpoint incompatible (`incremental.py:112-120`; worker SQL), so without the bootstrap every next price change ends `REPAIR_REQUIRED` for all 868 instruments.

**Blockers today (INFERENCE from code, not executed; ERRORS D27).** `backfill.py --all-source-tickers` aborts at IHSG; `bootstrap_states.py` raises at IHSG; both predate M219; `backfill.py` has no bond path; every other writer (§2) imports engine/incremental and must change in step.

**Measured cost (FACT, docs).** v2 full rewrite: 844 tickers / 1.318 M rows in 258 s (`RAILWAY_CHANGELOG.md:727`). 868-instrument shadow: 311.7 s (`INCREMENTAL_FINALITY.md`). INFERENCE: a full rewrite adds about 1.39 M new row versions to an already sparse heap.

**Access (FACT).** Reading F04 from EDGE needs a new grant to `terminal_market_reader` or another read path; edge-bff's role reads no public table.

### 13. Documentation drift (FACT)

- `_INDEX` `Table_Catalog.update_rule` says daily routing is not enabled; stockbit-updater refreshes it daily (ERRORS C09).
- `INDICATOR_ALIGNMENT.md:13` and `:43` say 24 candlestick codes; the engine has 25 (ERRORS C11).
- `INDICATOR_ALIGNMENT.md` §2 "atr_14 / adx_14 differ in warm-up" describes the old HTML engine; the current TS matches F04 (section 04). Not recorded as drift: that document is a 2026-10-25 inspection of the uploaded HTML engine, which the row describes correctly.
- `DATABASE_CATALOG.md:108` and `FEATURE04_TECHNICAL_INDICATOR.md` counts are 2026-10-11 snapshots (844 / 1,318,633 and 24 / 60,409); live is 1,328,595 / 60,643.
- Catalog label v4 against engine string v3.


## 53-INDICATOR COVERAGE MATRIX

Approval item 4. Rows come from `audit/matrix_a.json` (I01–I27) and `audit/matrix_b.json` (I28–I53), with every `row_corrections` entry of `audit/verify_matrix_a.json`, `audit/verify_matrix_b.json` and `audit/verify_feature04.json` applied. Evidence notation as in the header: `audit/<area>.md` and `audit/verify_<area>.json` (reports and verifications), `evidence/<area>/<file>` (raw outputs), all relative to `verification/screener/`; repository `path:line` citations are at `main` `010af1e`. Raw evidence: `evidence/matrix_a/`, `evidence/matrix_b/`, `evidence/verify_matrix_a/`, `evidence/verify_matrix_b/`, `evidence/verify_feature04/`.

How the checks were made (FACT):
- The TS module `apps/edge-bff/terminal/src/calc/indicators.ts` `F` was run unchanged under node 22.
- TA-Lib 0.6.8 on C 0.6.4 (the Feature 04 pin) ran in a scratch venv.
- Live price and Feature 04 rows came through pgweb, read-only: 6 + 7 tickers for I01–I27 plus a full-market pass (844 tickers, 114,544 F04 rows); 26 + 18 tickers for I28–I53.
- Registry defaults come from `apps/edge-bff/backtest/src/core/backtest-registry.json` (`evidence/verify_feature04/registry_list.txt`). Its source hashes equal the current `indicators.ts` and `indRegistry.json`.
- The user's workbook gives each default its own evidence status and each indicator a calculation readiness; column Workbook and footnote 24 carry both, because a registry default is not always a verified default.

### Legend

| Column | Codes |
|---|---|
| Workbook | Status of the default in the user's workbook: V verified, P proposed, RP reference profile (not a UI default), RF reference formula (not a UI default); `A/B` when parameters differ (details in [24]); `PL` calculation readiness PARTIAL_LOGIC; `—` no parameter [24] |
| Inputs | O H L C V; `src` = the chosen source (default close) |
| Warm-up | `fv n` = first valid bar index (0-based). Class: **W** finite window (start-independent from `fv`), **W\*** finite in exact arithmetic but floating-point residue carries history, **R** recursive, **S** state machine, **C** cumulative (never settles), **P** point-wise, **A** calendar-anchored. Numbers are bars to converge after a later history start: median/p95/max, or a range [1] |
| F04 stored | Feature 04 column(s); `D:` exact SQL derivation from F04 columns; `F01:` an equal `Feature_01_Stock_Daily` column; `—` none |
| F04 compat | `=` identical, or exact by arithmetic for a `D:` derivation (max relative difference given), when TS computes from the ticker's first price row [2]; `≈` near-identical; `n/a` not stored |
| BT | Backtest calculates it: every key is `F.<key>` through `conditions.ts` `Calc.out`, `available_for_backtest=true` [23] |
| TA-Lib | TA-Lib 0.6.8 function and whether it equals TS at registry defaults: `=` equal (rel ≤ 3.6e-16); `≠` different convention; `build ≈` equal when composed from TA-Lib pieces; `none` |
| Custom impl | `No` = TS `F` covers it; `Outside TS:` what a non-TS (for example Python) path must port; `Transform:` a screener-layer transform on top of `F` outputs that the prototype's conditions need |
| Default path | **DECIDED** (P2 a, 2026-10-28; the mechanism is PROPOSED). Every registry default is computed by `F` over full history once per rack publication into the in-memory snapshot (TARGET ARCHITECTURE §6.7). `oracle` names the Feature 04 column, its exact derivation (`D:`) or the Feature 01 (`F01`) column used as the test oracle only, never as a runtime read. Custom parameters are always dynamic on full history [22]. Not offered: raw level thresholds on I40, I41, I44, I50, I51 [18] |
| Conditions | V value test; S state on the evaluation bar; E event within N sessions; `x` crosses; R rising vs k bars ago |
| Label | Applies to every cell except Default path, which follows the decided P2 (a) with a PROPOSED mechanism |

### Matrix

| ID | Name | Key | Default params | Workbook | Inputs | Outputs | Warm-up / history | F04 stored | F04 compat | BT | TA-Lib / = TS | Custom impl | Default path | Conditions | Label |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| I01 | SMA | sma | len 20, src close | P | src | sma | fv 19; W | sma_20 (+sma_50 at len 50) | = (rel 0) | yes | SMA = | No | Snapshot; oracle sma_20 (sma_50 at length 50) | S close >/<; E close x; V % dist; R slope; fast x slow | FACT |
| I02 | EMA | ema | len 20, src close | P | src | ema | fv 19; R 99/118/128 | — at 20; ema_12/26/50/200 | = for stored lengths (rel 0) | yes | EMA = | No | Snapshot; oracle ema_12/26/50/200 at those lengths only (none at 20) | as I01 | FACT |
| I03 | WMA | wma | len 20, src close | P | src | wma | fv 19; W | — | n/a | yes | WMA = | No | Snapshot; no oracle | as I01 | FACT |
| I04 | Hull MA | hma | len 9, src close | RP/P | src | hma | fv 10; W | — | n/a | yes | none; WMA build ≈ 8e-12 | Outside TS: floor(n/2), floor(√n) | Snapshot; no oracle; cap length [9] | as I01; R turning | FACT |
| I05 | KAMA | kama | len 10, fast 2, slow 30, src close | P | src | kama | fv 10; R 105/191/1,109 [3] | — | n/a | yes | KAMA = at 2/30 only | Outside TS: fast/slow ≠ 2/30 | Snapshot; no oracle | S close >/<; E x; V % dist; R slope | FACT |
| I06 | MACD | macd | 12/26/9, src close | V/P | src | macd, signal, histogram | fv 25 (sig/hist 33); R 159/184/199 (sig max 205) | macd, macd_signal, macd_histogram | = (rel 0) | yes | MACD ≠ [4]; EMA−EMA + EMA signal build = | Outside TS: never `talib.MACD` | Snapshot; oracle macd, macd_signal, macd_histogram | E macd x signal; S macd > signal; E x 0; hist sign/rising; divergence | FACT |
| I07 | ADX / DMI | adx | di 14, adx 14 | RP; PL | H L C | adx, plus_di, minus_di | DI fv 14, ADX fv 27; R ADX 202/234/668, DI max 498 | adx_14 only (no ±DI) | = adx (max rel 1.25e-15) | yes | ADX, PLUS_DI, MINUS_DI = when di = adx | Outside TS: di ≠ adx | Snapshot; oracle adx_14 (ADX only; ±DI none) | V ADX > 20/25; R ADX rising; S +DI > −DI; E DI x | FACT |
| I08 | Aroon | aroon | len 14 | P | H L | aroon_up, aroon_down | fv 14; W | — | n/a | yes | AROON = | No | Snapshot; no oracle | V up > 70, down < 30; E up x down; S up > down | FACT |
| I09 | Supertrend | supertrend | atr 10, factor 3 | P; PL | H L C | supertrend, direction | fv 10; S+R line 92/130/228, dir 21/71/268 | — (F04 has atr_14, not atr_10) | n/a | yes | none | Outside TS: port | Snapshot; no oracle; require factor > 0 [5] | S dir = +1; E flip; V % dist | FACT |
| I10 | Donchian | donchian | len 20 | V | H L | upper, basis, lower | fv 19; W | — (F01 `high_20d` is max(close), not max(high)) | n/a | yes [6] | MAX/MIN = | Transform: prior-bar band | Snapshot (prior-bar form); no oracle | E/S breakout vs prior bar; V % position; width % | FACT |
| I11 | Keltner | keltner | len 20, src close, mult 2, EMA, ATR style, atr 10 | V/P; PL | H L C + src | upper, basis, lower | fv 19; R ~99/118/139 | — | n/a | yes | none; EMA + ATR build ≈ 8e-16 | No | Snapshot; no oracle | S close > upper / < lower; E x; V % position; squeeze vs BB | FACT |
| I12 | Parabolic SAR | psar | .02 / .02 / .2 | V; PL | H L (registry lists H L C) | sar, direction | fv 1; S: SAR 23/79/288, dir 11/61/195 | — | n/a | yes | SAR / SAREXT = | No | Snapshot; no oracle | S dir = +1; E flip; V % dist | FACT |
| I13 | RSI | rsi | len 14, src close | V | src | rsi | fv 14; R 164/191/459 [7] | rsi_14 | = (rel ≤ 2.2e-16) | yes | RSI = | No | Snapshot; oracle rsi_14 | V < 30 / > 70 / between; E level x; R rising | FACT |
| I14 | Stoch RSI | stoch_rsi | 14/14/3/3, src close | RP/P | src | k, d | K fv 29, D 31; R K 185/456/713, D max 715 | — (rsi_14 is only its input) | n/a | yes | STOCHRSI fastd + SMA build =; fastk ≠ | Outside TS: use the build | Snapshot; no oracle | V K/D < 20 / > 80; E K x D; S K > D | FACT |
| I15 | Stochastic | stochastic | 14/3/3 | V | H L C | k, d | fv 17; W | — | n/a | yes | STOCH = | No | Snapshot; no oracle | V < 20 / > 80; E K x D; S K > D | FACT |
| I16 | Williams %R | williams_r | len 14, src close | V | H L + src | williams_r | fv 13; W | — | n/a | yes | WILLR = (close only) | Outside TS: src ≠ close | Snapshot; no oracle | V < −80 / > −20; E level x | FACT |
| I17 | ROC | roc | len 9, src close | V | src | roc (%) | fv 9; W | — at 9; F01 return_5d/20d/60d_pct = ROC 5/20/60 [8] | n/a (F01 = at 5/20/60) | yes | ROC = | No | Snapshot; no oracle at length 9; F01 return_5d/20d/60d_pct at 5/20/60 | V % thresholds; sign; E x 0; rank | FACT |
| I18 | Momentum | momentum | len 10, src close | RP/P | src | momentum (Rp) | fv 10; W | — | n/a | yes | MOM = | No | Snapshot; no oracle | sign; E x 0 (not comparable across tickers) | FACT |
| I19 | CCI | cci | len 20, const 0.015 | RP/P | H L C | cci | fv 19; W | — | n/a | yes | CCI = at 0.015 | Outside TS: const ≠ 0.015 | Snapshot; no oracle; cap length [9] | V < −100 / > +100; E level x | FACT |
| I20 | CMO | cmo | len 14, src close | P | src | cmo | fv 14; W\* 14/14/425 [10] | — | n/a | yes | CMO ≠ (Wilder-smoothed); SUM build = | Outside TS: never `talib.CMO` | Snapshot; no oracle | V < −50 / > +50; E x 0 | FACT |
| I21 | TSI | tsi | long 25, short 13, sig 7, src close | RF/P | src | tsi, signal | fv 37 (sig 43); R 180/206/510 (sig max 553) | — | n/a | yes | none | Outside TS: port | Snapshot; no oracle | E tsi x signal; E x 0; V ±25 | FACT |
| I22 | TRIX | trix | len 15, src close | P | src | trix (%) | fv 43; R 128/142/151 | — | n/a | yes | TRIX = | No | Snapshot; no oracle | sign; E x 0 | FACT |
| I23 | Ultimate Osc | ultimate_osc | 7/14/28, weights 4/2/1 | RP/P | H L C | uo | fv 28; W\* 28/28/1,087 [11] | — | n/a | yes | ULTOSC = (4/2/1, ascending periods) | Outside TS: other weights or order | Snapshot; no oracle (full history) | V < 30 / > 70; E level x | FACT |
| I24 | Awesome Osc | awesome_osc | 5/34 | P | H L | ao (Rp) | fv 33; W | — | n/a | yes | none; MEDPRICE + SMA build ≈ | No | Snapshot; no oracle | sign; E x 0; R rising; saucer | FACT |
| I25 | PPO | ppo | 12/26/9, src close | P | src | ppo, signal, histogram (%) | fv 25 (sig/hist 33); R 165/187/206 | D: line = 100·(ema_12−ema_26)/ema_26 | line = (rel ≤ 2.8e-16); signal n/a | yes | PPO matype 1 + EMA signal =; default matype 0 ≠ | No | Snapshot; oracle D: line only | V % thresholds; E ppo x signal; E x 0; hist sign | FACT |
| I26 | Balance of Power | bop | none | — | O H L C | bop (−1..1) | fv 0; one bar | — | n/a | yes | BOP = | No | Snapshot; no oracle | V > 0 / > 0.5; sign [12] | FACT |
| I27 | Bollinger Bands | bollinger | len 20, src close, std 2, basis SMA | V/P | src (+V for VWMA basis) | upper, basis, lower | fv 19; W (SMA/WMA basis), R (EMA/RMA basis) [13] | bb_upper_20, bb_middle_20, bb_lower_20 | = (rel 0) | yes | BBANDS = (SMA/EMA/WMA basis); RMA/VWMA none | Outside TS: RMA/VWMA basis | Snapshot; oracle bb_upper/middle/lower_20 | S close > upper / < lower; E x; close vs basis; squeeze needs BBW history | FACT |
| I28 | Bollinger %B | bollinger_pctb | 20, close, 2, SMA | V/P | src | percent_b | fv 19; W [13] | D: (close−bb_lower_20)/NULLIF(bb_upper_20−bb_lower_20,0) | = (rel 0) | yes | BBANDS-derived = | No | Snapshot; oracle D: %B | V < 0 / > 1 / between; E level x | FACT |
| I29 | Bollinger Bandwidth | bollinger_width | 20, close, 2, SMA | V/P | src | bandwidth (%) | fv 19; W [13] | D: 100·(bb_upper_20−bb_lower_20)/NULLIF(bb_middle_20,0) | = (rel ≤ 3.1e-16) | yes | BBANDS-derived = | Transform: N-bar min (squeeze) | Snapshot; oracle D: bandwidth | V < x%; R rising; squeeze = N-bar low | FACT |
| I30 | ATR | atr | len 14, smoothing RMA | V | H L C | atr (Rp) | fv 14; R ~190–271 [1] | atr_14 | = (rel 0) | yes | ATR = (RMA); SMA/EMA/WMA = MA(TRANGE) | Transform: ATR vs own MA | Snapshot; oracle atr_14 | R rising; expansion vs own MA (Rp: use NATR for thresholds) | FACT |
| I31 | NATR | natr | len 14, smoothing RMA | P | H L C | natr (% of close) | fv 14; R ~188–277 | D: 100·atr_14/close | = (rel ≤ 2.8e-16) | yes | NATR = | No | Snapshot; oracle D: 100·atr_14/close | V > 3%; between; R rising | FACT |
| I32 | Std Deviation | stddev | len 20, close, population | P | src | stddev (Rp) | fv 19; W [13] | D: (bb_upper_20−bb_middle_20)/2 | = by exact arithmetic (rel ≤ 1.2e-14; 1.3e-9 on flat BNBR windows) | yes | STDDEV = (population); sample: none | Outside TS: % of price variant | Snapshot; oracle D: (bb_upper_20−bb_middle_20)/2 | V in Rp only (not comparable across tickers) | FACT |
| I33 | Historical Volatility | hist_vol | len 20, close, log, 252 | P | src | historical_volatility (% annualised) | fv 20; W | — (F01 volatility_20d_ann_pct is another formula [14]) | n/a | yes [15] | none; STDDEV(LN)·√252·100 build ≈ 3.7e-13 | Transform: short/long HV ratio | Snapshot; no oracle (F01 volatility is another formula [14]) | V > 30%; between; R rising | FACT |
| I34 | Avg Daily Range | adr | len 14 | P | H L | adr (Rp) | fv 13; W [13] | — | n/a | yes | none; SMA(H−L) build ≈ | Outside TS: ADR % | Snapshot; no oracle | Rp only; avoid "ADR > 0" [13] | FACT |
| I35 | Volume SMA | volume_sma | len 20 | P | V | volume_sma (shares [16]) | fv 19; W | F01: volume_avg_20d | F01 = (rel ≤ 3.2e-12) | yes | SMA(V) = | No | Snapshot; oracle F01 volume_avg_20d | S V > avg; E V x avg; liquidity filter | FACT; unit INFERENCE |
| I36 | Volume EMA | volume_ema | len 20 | P | V | volume_ema (shares) | fv 19; R ~146–205 | — | n/a | yes | EMA(V) = | No | Snapshot; no oracle | S V > avg; E V x avg | FACT |
| I37 | Relative Volume | rvol | len 20 (current bar included) | P; PL | V | rvol (×) | fv 19; W | F01: volume_ratio_20d | F01 = (rel ≤ 1.5e-11) | yes [17] | none; V/SMA(V) build ≈ 1.2e-11 | Outside TS: exclude-current-bar variant | Snapshot; oracle F01 volume_ratio_20d | V > 1.5 / > 3; E level x | FACT |
| I38 | PVO | pvo | 12/26/9 | P | V | pvo, signal, histogram (%) | fv 25 (sig/hist 33); R ~233–330 | — | n/a | yes | PPO(V, matype 1) + EMA signal = | No | Snapshot; no oracle | V > 0; E pvo x signal; S hist > 0 | FACT |
| I39 | Volume ROC | volume_roc | len 10 | P | V | volume_roc (%) | fv 10; P (two bars) | — | n/a | yes | ROC(V) ≠ only where V[t−n] = 0 (TS null, TA-Lib 0) | No | Snapshot; no oracle | V > 50% / > 200%; E level x | FACT |
| I40 | OBV | obv | none | — | C V | obv (cumulative) | fv 0; C [18] | — | n/a | yes | OBV = | Transform: MA of output, k-bar change, N-bar high | Snapshot; no oracle; derived states only, no raw level thresholds [18] | S vs own MA; E x own MA; N-bar high; R k-bar; divergence | FACT |
| I41 | PVT | pvt | none | — | C V | pvt (cumulative) | fv 0; C [18] | — | n/a | yes | none | as I40 | Snapshot; no oracle; derived states only, no raw level thresholds [18] | as I40 | FACT |
| I42 | VWMA | vwma | len 20, src close | RP/P | src + V | vwma | fv 19; W | — | n/a | yes | none; SUM(C·V)/SUM(V) build ≈ 1.2e-11 | Transform: % distance | Snapshot; no oracle | S close >/<; E x; V % dist | FACT |
| I43 | Anchored VWAP | vwap | anchor Session, src hlc3, StdDev bands, ×1 | V/P; PL | src fields + V + dates | vwap, upper1, lower1 | fv 0 per period; A [19] | — | n/a | yes | none (Session = TYPPRICE) | Transform: % distance | Snapshot; no oracle. Week, Month, Quarter and Year anchors only (P17 a, decided): the registry default Session is not offered, so I43 is pre-warmed at anchor Week (P17's consequence, PROPOSED) | S close >/<; E x; bands; % dist | FACT; Decade/Century start-dependence UNKNOWN [19] |
| I44 | A/D Line | adl | none | — | H L C V | adl (cumulative) | fv 0; C [18] | — | n/a | yes | AD = | as I40 | Snapshot; no oracle; derived states only, no raw level thresholds [18] | as I40 | FACT |
| I45 | Chaikin Money Flow | cmf | len 20 | P | H L C V | cmf (−1..1) | fv 19; W | — | n/a | yes | none; build ≈ (abs < 1e-9 near 0) | No | Snapshot; no oracle | V > 0 / > 0.2 / < −0.2; E x 0 | FACT |
| I46 | Chaikin Oscillator | chaikin_osc | 3/10 | RF | H L C V | chaikin_osc | fv 9; R ~68–105 (9 from a flat start) | — | n/a | yes | ADOSC = | No | Snapshot; no oracle | sign; E x 0; R rising | FACT |
| I47 | Money Flow Index | mfi | len 14 | V | H L C V | mfi (0–100) | fv 14; W | — | n/a | yes | MFI = | No | Snapshot; no oracle | V < 20 / > 80; E level x | FACT |
| I48 | Force Index | force_index | len 13 | V | C V | force_index | fv 13; R ~59–135 | — | n/a | yes | none; EMA(ΔC·V) build ≈ 4.1e-11 | No | Snapshot; no oracle | sign; E x 0 | FACT |
| I49 | Ease of Movement | eom | len 14, scale 1e6 | RF/P | H L V | eom | fv 14; W (V = 0 nulls the raw value and restarts the SMA) | — | n/a | yes | none | No | Snapshot; no oracle | sign; E x 0 | FACT |
| I50 | NVI | nvi | initial 1000 | P | C V | nvi (cumulative) | fv 0; C [18] | — | n/a | yes | none | Transform: MA(255) of output | Snapshot; no oracle; derived states only, no raw level thresholds [18] | vs own MA [18]; R k-bar ratio | FACT |
| I51 | PVI | pvi | initial 1000 | P | C V | pvi (cumulative) | fv 0; C [18] | — | n/a | yes | none | as I50 | Snapshot; no oracle; derived states only, no raw level thresholds [18] | as I50 | FACT |
| I52 | Klinger VO | kvo | 34/55/13 | RF; PL | H L C V | kvo, signal | fv 55 (sig 67); R ~418–624 (sig 440–641) | — | n/a | yes | none | No: `F`'s classic Klinger, approved as I52 (P16 a, decided with the go) [20] | Snapshot; no oracle [20] | E kvo x signal; S kvo > 0 | FACT; definition DECIDED (P16 a) |
| I53 | Market Facilitation | market_fi | scale 1 | P | H L V | market_fi | fv 0; P | — | n/a | yes | none | Transform: Williams 4-state | Snapshot; no oracle | R vs previous bar; 4-state (custom) | FACT |

### Footnotes

1. **Warm-up method.** I01–I27: history cut at bar 1000 on all 531 tickers with ≥ 1,500 bars; tolerance 1e-6 × max|full value|; median/p95/max bars to converge (`evidence/verify_matrix_a/v_converge_max.txt`). I28–I53: 6 tickers × 3 later starts (2021-01-04, 2024-01-02, 2025-01-02); tolerance 1e-9 × scale; min–max bars (`evidence/verify_matrix_b/startdep_report.txt`). The figure depends on the tolerance: ATR needs about 190–271 bars at 1e-9 × scale but about 50–80 at 0.1% (`verification/terminal_api/INDICATOR_ALIGNMENT.md:30-32`). FACT.
2. **F04 equality condition.** Equal only when TS starts at the ticker's first price row, as F04 and the publisher do. From only the last 260 bars, last-bar `ema_200` differs by 0.13–1.35% and `ema_50` by up to 8.3e-6; from 500 bars, `ema_200` still differs by 0.10–0.19% (`evidence/verify_feature04/derive_check.out`). Market-wide, the 15 stored columns match TS with the same first bar and 0 null mismatches (`evidence/verify_matrix_a/v_market.txt`). F04 stores only `source=close`. FACT.
3. **KAMA.** On flat or noisy stocks the smoothing constant falls to (2/31)², about 0.0042, so start errors decay slowly; with a 1,000-bar tail BABP's latest KAMA is still 1.3e-3 off. FACT (`evidence/verify_matrix_a/v_converge_max.txt`).
4. **talib.MACD.** It reseeds the fast EMA at the slow look-back and outputs from bar 33 instead of 25. In warm-up it differs by up to 150% relative (ASII bars 33–60); PRDL (75 bars) never converges. The build `talib.EMA(12) − talib.EMA(26)` with signal `talib.EMA(macd[25:], 9)` is equal (rel 0). FACT (`evidence/verify_matrix_a/v_talib.txt`, `evidence/verify_matrix_a/v_talib2.txt`).
5. **Supertrend factor 0.** The registry allows `factor` min 0. At factor 0, BBRI has 70 up-trend bars with the line above the close and 1,128 flips in 2,115 bars (60 at factor 3). FACT (`evidence/verify_matrix_a/v_st0.txt`). Recorded as ERRORS M257 (2026-10-28).
6. **Donchian same-bar defect.** `upper[t]` includes `H[t] ≥ C[t]`, so `close > upper` and `close crosses_above upper` can never be true. Through the Backtest's `compare()` on 844 tickers: 0 hits, against 29,041–54,652 hits with prior-bar bands. The Backtest's `price_action breakout` already uses the prior bar (`conditions.ts:126, 170-172`); the trap is the generic indicator condition with a price left-hand side. Not in `ERRORS_AND_SOLUTIONS.md` at the audit (grep "Donchian": 0); recorded 2026-10-28 as ERRORS M255. FACT (`evidence/verify_matrix_a/v_market.txt`).
7. **RSI flat stretches.** Wilder RSI keeps its last value through flat stretches (37,100 of 44,033 flat 14-change windows have RSI ≠ 0), as TA-Lib does; it snaps to 0 only when the sums fall below 1e-14. An "RSI < 30" screen can match a flat or suspended stock on an old value. FACT (`evidence/verify_matrix_a/v_flat.txt`).
8. **ROC vs Feature 01.** `return_Nd_pct` is `(close::double / NULLIF(close_Nd_ago,0) − 1) × 100` with a row lag (migration `20260912_001` l.163-191). It equals `F.roc` at lengths 5/20/60 exactly (max abs 0, 0 null mismatches on BBRI, BLTA, GOTO). A zero base gives NULL there and 0 in TS; no zero closes exist. FACT (`evidence/verify_matrix_a/v_f01.txt`; corrects the audit's "untested" INFERENCE).
9. **Window-scan cost.** HMA, Aroon, Donchian, Stochastic, Stoch RSI, Williams %R and CCI are O(N·n), and registry integer lengths have `min: 1` and no maximum (`registry.ts:62` enforces only `max`). Whole market at n = 1000 on one core: CCI 7.93 s, Stoch RSI 2.63 s, Williams %R 2.58 s, HMA 2.19 s, Stochastic 2.05 s, Donchian 1.26 s, Aroon 1.23 s; CCI at default 0.56 s. FACT (`evidence/verify_matrix_a/v_bench.txt`).
10. **CMO.** The n-bar sums are running sums, so on split-adjusted non-integer history a flat window can return ±100 or residue instead of null: 3,231 of 44,033 flat 14-change windows on 17 tickers (BABP 2024-04-24 = +100). The prototype returns 0. FACT (`evidence/verify_matrix_a/v_flat.txt`).
11. **Ultimate Oscillator.** Running-sum residue: UO is outside [0, 100] on 2,972 bars market-wide, and 3,218 of 31,764 fully flat 28-bar windows give UO ≠ 0. No artefact on the 2026-10-27 bar. FACT (`evidence/verify_matrix_a/v_flat.txt`).
12. **BOP.** 0 whenever H = L or C = O: on 2026-10-27, 76 stocks have BOP exactly 0 while only 4 have H = L. FACT (`evidence/verify_matrix_a/v_market.txt`).
13. **Flat-window residue (Bollinger family, StdDev, ADR).** TA-Lib-order running sums (`kStd`, E[x²]−E[x]²) carry residue from earlier fractional history, even on integer-price flat windows. Market-wide 3,299 of 41,412 flat 20-close windows have upper > basis. In the last year 502 equity ticker-days on 16 tickers have exactly zero width (%B null, BBW 0); 100 equity ticker-days on BABP and BCAP (flat at 50) have a residue width of 4.9e-7 to 5.4e-7 × close, where TS %B is 0.5 (null in the prototype); the other 54 of the audit's 154 rows are bonds. ADR residue goes both ways: BNBR 905 negative values, BABP 274 positive values where the true range is 0. SQL derivations need `NULLIF(…, 0)` because TS `div()` returns null on a zero denominator (`indicators.ts:36`). FACT (`audit/verify_matrix_b.json` refuted `b-flat-window-fp`; `evidence/verify_feature04/v26_invalid.out`).
14. **HV vs Feature 01.** `volatility_20d_ann_pct` is `stddev_samp` of simple returns (live `refresh_feature_01_stock_daily`); I33 is the population SD of log returns. On 20 tickers (28,319 bars): per-ticker median difference 2.4–3.4% (about the √(20/19) factor), p95 6.9%, max 23.2% (ACST). Do not show both as "20-day volatility". FACT (`evidence/verify_matrix_b/hv_vs_f01.txt`). Decided with the go: P18 (a), I33 is named "Historical volatility (log, population)" and Feature 01's value never carries that name.
15. **`annualization_periods` is floored.** `LENGTH_KEYS` in `def()` matches `_periods` (`indicators.ts:239`), so 252.9 behaves as 252 (the floor is at `indicators.ts:249`), while the registry types it `number` and `resolveParams` lets the fraction through. FACT. Recorded as ERRORS M258 (2026-10-28).
16. **Volume unit.** Price volume equals the Regular-board share volume (`sum(buy_lots) × 100`) on 21 of 21 samples, and `Feature_01.volume_avg_20d` is catalogued as Shares (VERIFIED). The price table's own unit is undocumented (ERRORS D07). For 180 split-adjusted tickers volume is fractional (77,996 rows). FACT (samples) / INFERENCE (unit of the price column).
17. **RVOL `include_current_bar`.** `F.rvol` always includes the current bar (user decision 2026-10-25, `EXEC.md:7881`). The registry lists the parameter as `not_accepted` with workbook default `false`, and `regToCondition` drops it when it equals `false`, so a card labelled "exclude current bar" is computed with it included. The prototype's `x_rvol`, its "Volume spike" and the Backtest `volspike` divide by the previous N sessions. `AI_formula_reference` CALC_062 excludes the bar; CALC_230 includes it. FACT (`audit/reuse.md` §7 item 2). Recorded as ERRORS M256 (2026-10-28); the Screener hides the parameter (P6 a, decided with the go).
18. **Cumulative series (OBV, PVT, A/D, NVI, PVI).** The level depends on the first bar forever: last-bar relative differences after a 2021/2024/2025 start reach 93% (OBV), 170% (PVT), 107% (A/D), 370% (PVI) and about 96,800% (NVI, AGRO). Start-independent: k-bar change, ratio, N-bar high, and level vs SMA(n) in exact arithmetic (on flat windows that state is a floating-point tie: BNBR 358 of 358 disagreements; needs a tie rule). Start-dependent: level vs EMA(n), which the prototype uses (EMA 20; EMA 255 for NVI/PVI). The EMA-255 seed weight reaches 1e-9 only after about 2,650 bars, longer than any stock's history (2,125), and 13 stocks have fewer than 300 bars. No absolute thresholds or cross-ticker comparisons. FACT (`evidence/verify_matrix_b/startdep_report.txt`, `evidence/verify_matrix_b/derived_state_report.txt`).
19. **VWAP anchors.** With anchor Session on daily bars, vwap = hlc3 within 2e-16; the bands differ from vwap on 1,611 of 28,220 bars by up to 4.6e-8 × vwap, and on 57 bars "close > vwap" and "close > upper1" disagree. A Session condition reduces to close vs typical price. Week/Month/Quarter/Year anchors are start-independent if the load starts on a period boundary. Decade and Century anchors span all stored history (`periodKey`, `indicators.ts:591-602`), so they behave like cumulative rows: INFERENCE from code, UNKNOWN on live data (check: compute Decade and Century anchors from two later history starts and compare the last bar). The prototype returns the price instead of null when period volume is 0 (line 956). FACT except as marked. Decided with the go of 2026-10-28: P17 (a), only the Week, Month, Quarter and Year anchors are offered.
20. **KVO definitions.** Three disagree: TS uses classic Klinger with `|2(dm/cm − 1)|` (`indicators.ts:547-556`); the workbook outline has no `abs`; the prototype (line 966) is a signed-volume EMA on the hlc3 change with no dm/cm. Attributing the prototype's form to TradingView is INFERENCE. Decided with the go of 2026-10-28: P16 (a), `F`'s classic Klinger (UNKNOWNS / PRODUCT DECISIONS). Also: RANS (74 bars) gets only 7 signal values. FACT.
21. **Index and bonds.** Volume is NULL for IHSG (2,127 rows), so every volume indicator has no value for the index; a VWMA basis on I27 makes all IHSG bands null and the Backtest raises `INDICATOR_OUTPUT_EMPTY`. I27 accepts a VWMA basis but I28/I29 do not. FACT (`audit/verify_matrix_a.json` additional findings).
22. **Custom parameters.** A short tail is unsafe for recursive rows and long lengths: with only the last 1,000 bars, EMA 200 differs at the latest bar on 508 of 575 tickers (worst 6.2e-4 rel); with 500 bars it is up to 7.7% off (SAPX 312.44 vs 336.37) and MACD 50/200/20 can flip sign. A uniform "full history from the first price row" rule is the only safe one. FACT (`evidence/verify_matrix_a/v_tail_custom.txt`).
23. **Backtest condition model.** All 53 compute in the Backtest, but its conditions have 4 operators (`gt`, `lt`, `crosses_above`, `crosses_below`; `conditions.ts:25`) and one indicator instance per condition (`conditions.ts:92-96`). It accepts "price vs output" for every indicator, including meaningless pairs such as close vs RVOL. The registry `inputs` ignore the chosen source (I28/I29/I32/I33 list [C] even with another source); the TS `def()` derives the needed fields from the source, and a loader must follow `def()`. FACT.
24. **User workbook status (FACT).** Source: the user's workbook `Technical_Indicators_53_Frontend_Display_Spec.xlsx` (not committed), its per-parameter default evidence and per-indicator calculation readiness, read by `evidence/matrix_a/read_xlsx.py`, `evidence/verify_matrix_a/xlsx_dump.py` and `evidence/verify_matrix_a/xlsx_params.py` (their text dumps are local, not committed: user file content); summarised in `audit/matrix_a.md` (column "default (evidence)") and in the PARTIAL_LOGIC corrections of `audit/verify_matrix_a.json` and `audit/verify_matrix_b.json`. VERIFIED_DEFAULT: I06 (lengths), I10, I11 (length, source), I12, I13, I15, I16, I17, I27, I28 and I29 (length, source, std_dev), I30, I43 (source only), I47, I48. REFERENCE_PROFILE_NOT_UI_DEFAULT: I04, I07, I14, I18 and I19 (lengths), I23 (periods), I42 (length). REFERENCE_FORMULA_NOT_UI_DEFAULT: I21 (long length), I46, I49 (length), I52. No parameter (NOT_APPLICABLE): I26, I40, I41, I44. Every other parameter default is PROPOSED_DEFAULT. Calculation readiness PARTIAL_LOGIC: I07, I09, I11, I12, I37, I43, I52; the other 46 are FORMULA_SPEC. So only 9 rows have every default verified (I10, I12, I13, I15, I16, I17, I30, I47, I48), and a "Default" chip that shows the registry default would present proposed or reference profiles as defaults on the others. Decided with the go of 2026-10-28: P21 (a), "Default" shows the registry default, labelled "proposed default" where the workbook does not verify it; any change of a default goes through a registry release (P6).

### Patterns

**1. Stored, derivable or dynamic (FACT unless marked).**

| Group | Indicators | Count |
|---|---|---|
| Stored in F04 at the registry default | I01, I06, I13, I27, I30 | 5 |
| Derived exactly from F04 columns | I28, I29, I31, I32 | 4 |
| Partly served by F04 | I07 (ADX only), I25 (line only) | 2 |
| Equal to a Feature 01 column at the default | I35, I37 (I17 only at lengths 5/20/60) | 2 |
| No stored default anywhere | the other 40 | 40 |

DECIDED (P2 a, 2026-10-28; mechanism PROPOSED): every default is pre-warmed. All 53 indicators (76 outputs) are computed by `F` in memory once per publication (TARGET ARCHITECTURE §6.7), so no indicator is dynamic-only at its default, and every custom parameter set is dynamic [22]. Oracle coverage at the default, for tests only: Feature 04 stored or exact derivation, 9 full (I01, I06, I13, I27, I28, I29, I30, I31, I32) and 2 partial (I07 ADX output, I25 line); Feature 01, 2 (I35, I37), plus I17 at lengths 5/20/60 only; no oracle, 40. The audit-stage split (Feature 04 or a derivation 9, Feature 01 2, snapshot 25, snapshot or dynamic 3, dynamic only 14) assumed runtime reads of Feature 04 and Feature 01, which P2 (a) rejects; it is superseded.

**2. History dependence (FACT).**
- **Finite window** (exact from the first valid bar; needs n−1 bars plus the event window): I01, I03, I04, I08, I10, I15–I19, I24, I27 (SMA basis), I28, I29, I32–I35, I37, I42, I45, I47, I49; one bar or point-wise: I26, I39, I53.
- **Window with residue** (exact parity ties to full history on flat stretches): I20 CMO (max 425 bars), I23 UO (max 1,087), and the Bollinger family, StdDev and ADR on flat windows [10, 11, 13].
- **Recursive:** I02, I05, I06, I07, I11, I13, I14, I21, I22, I25, I30, I31, I36, I38, I46, I48, I52; **state machines:** I09, I12. Typical convergence 100–250 bars; long tails on flat or illiquid stocks (KAMA 1,109 BABP; StochRSI 713 PCAR; ADX 668 BEKS; UO 1,087 BABP); KVO 418–641 bars and never settled from a 2025 start.
- **Cumulative:** I40, I41, I44, I50, I51 never settle [18]. **Calendar-anchored:** I43 [19].
- **Consequence (INFERENCE).** Default and custom values must be computed from each ticker's first price row to match Feature 04, the Terminal and the Backtest. A fixed tail of K = 500 bars reproduces default MACD/RSI/ATR/ADX within 1e-9 (KVO, flat-regime KAMA and the cumulative rows excepted), but not long custom lengths: EMA 200 still differs on 516 of 532 tickers at K = 1,500. Calendar windows are unsafe (XSPI has 64 bars since 2023-10-01) (`audit/benchmark.md` §2e).
- **Cost (FACT).** All 53 defaults over full history for the whole market take 8.1–10.2 s on one thread; peak RSS about 299 MB, nearly all input data (`evidence/benchmark/results/all53_full.metrics.json`). Loading the bars, not computing, dominates.

**3. TA-Lib and TS conventions (FACT).**
- **Approved formula contract (FACT).** User decision 2026-10-25 (`EXEC.md:7876-7878`): "Yang ada kita sesuaikan saja dengan feature 4, tapi jika tidak ada kita pakai HTML." Indicators that Feature 04 stores follow Feature 04 (TA-Lib seeds for ATR and ADX; RSI 0 on a flat window); the others follow the Terminal reference engine (the `TA` engine of `03-terminal-right-panel.html`). `indicators.ts` `F` implements this and is verified against Feature 04, TA-Lib and that engine (`apps/edge-bff/terminal/tests/calc/PARITY.md`, run 2026-10-25: 23 tickers, 1,619 tests, all passed). The screener prototype's `XI` and legacy helpers are not that engine and differ from `F` on 10 indicators at defaults (§5).
- **TradingView parity: UNKNOWN.** The workbook names a Pine `ta.*` function, alone or with a custom part, on 28 of the 53 rows (for example `ta.atr`, `ta.stdev`, `ta.vwma`, `ta.mfi`, `ta.vwap`; local workbook dumps, not committed), but no TradingView output was compared: the audit made no external call. By code, ATR and ADX follow TA-Lib, with no true range on bar 0. Check that settles it: export TradingView values for 3 tickers and the Pine-referenced indicators and compare them with `F`. Differences are reported, not adopted, unless the user changes the 2026-10-25 decision (UNKNOWNS U12).
- **EMA:** SMA seed of the first n values, then `(x − prev)·2/(n+1) + prev`; TA-Lib compatibility 0; TS `kEma` equals it (`indicators.ts:105-111`).
- **RSI:** SMA seed of the first n changes, then Wilder; 0 when gain + loss < 1e-14; holds its last value through flat stretches [7] (`indicators.ts:146-158`).
- **ADX / DI:** Wilder sums from bar 1 with no TR on bar 0; ADX seed = mean of the first `adx_smoothing` DX; DI from bar 14, ADX from bar 27 (`indicators.ts:170-196`). The "differs in warm-up" row of `INDICATOR_ALIGNMENT.md` §2 described the old HTML engine and is superseded.
- **ATR:** no TR on bar 0, SMA seed of TR[1..14], then Wilder; first value at bar 14 (`indicators.ts:133-145`). The user decision of 2026-10-25 (first bullet) aligned TS with F04. The prototype's engines put H−L on bar 0 (§5); whether TradingView does is not checked (TradingView parity, below).
- **MACD:** EMA12 − EMA26, both SMA-seeded from bar 0; signal EMA9 seeded at the first valid MACD (bar 25), so signal and histogram start at bar 33. `talib.MACD`/`MACDEXT` reseed the fast EMA and must not be used [4].
- **Stochastic:** slow K = SMA(fast K, 3), D = SMA(K, 3); fast K is 0 on a zero range; K stays null until D is valid, as in TA-Lib. **Stoch RSI:** K = TA-Lib `STOCHRSI(...).fastd` with SMA, D = SMA(K); TA-Lib `fastk` is unsmoothed and differs by up to 66.7 points.
- **Bollinger:** population SD around the window SMA for every basis type, via the running `kStd`; `AI_formula_reference` CALC_225 describes a two-pass SD (equal in exact arithmetic, different residue; ERRORS C10).
- **Other conventions:** CMO is Chande's plain sums (`talib.CMO` is Wilder-smoothed, 8.6–12.6 points off); PPO needs `matype=1` (default 0 is SMA); Volume ROC is null where the base volume is 0 (TA-Lib gives 0); OBV starts at the first bar's volume (user choice, 2026-10-25).
- **Null and warm-up semantics:** TS returns null before the first valid bar and restarts a series after a non-finite needed input (`def()`, `indicators.ts:244-275`). F04 resets on invalid OHLC or a missing equity volume (`engine.py:128-151`). The Backtest loader drops a row without four finite prices (`datafile.ts:137-160`). No live row triggers a difference today. In conditions, bar 0 is never true, NaN is false, a cross needs both sides on the previous bar, and an all-null series raises `INDICATOR_OUTPUT_EMPTY`, which must be treated as n/a per ticker.
- **Flat windows:** 9.3% of final daily bars have H = L (123,853), and 150,797 rows on 181 tickers have non-integer OHLC from back-adjustment, which drives the residue artefacts in [10, 11, 13]. INFERENCE: a liquidity or flat-bar filter is worth offering.

**4. Known defects and traps (FACT).** Donchian same-bar breakout [6] (ERRORS M255); RVOL `include_current_bar` label vs calculation [17] (M256); `annualization_periods` silently floored [15] (M258); no maximum length in the registry [9]; Supertrend factor 0 allowed [5] (M257); VWMA basis on IHSG [21]; registry `inputs` ignore the source [23]. INFERENCE: AI sandbox code that follows "TA-Lib first" and calls `talib.MACD`, `talib.CMO`, `STOCHRSI` fastk or `talib.PPO` with the default matype would disagree with the Screener; `AI_formula_reference` should name the equal builds.

**5. Where the prototype's own engines differ (FACT).** The prototype has two engines; neither is `F`.
- **`XI` (53 indicators, prototype 866-968).** On 5 tickers (full history, last 250 bars, 1e-9 × scale), 43 equal `F`. Always different: KVO (another formula, line 966), HV (sample SD, line 944), RVOL (excludes the current bar by default, line 948), OBV (starts at 0, line 951), PSAR (start from c[1] ≥ c[0] and reversal rule, line 918). Different on flat windows: KAMA (ER = 0 instead of 1, line 902), Stoch RSI, CCI, CMO (0 instead of null), UO. HMA at custom lengths (round vs floor of √n, line 901). ADX/ATR in warm-up (bar-0 TR = H−L with RMA seeds, lines 890, 905). Also VWAP returns the price when period volume is 0 (line 956), %B is null where `F` gives 0.5 on residue-width bands, MFI uses `q‖1e-9` (line 771), EOM gives 0 instead of null on V = 0 (line 963), Chaikin uses SMA-seeded EMAs (line 960), and NATR and PVO lack zero-denominator guards. A/D equals `F` (verifier correction).
- **Legacy helpers (prototype 753-777)** run every Technical preset: EMA seeded with the first value (754), MACD signal over NaN→0, RSI with `l‖1e-9`, STOCH warm-up filled with 50, ATR as a running mean with bar-0 TR = H−L (767). After warm-up they equal `F` on the 5 tickers, except the OBV offset and RSI in long flat stretches (DADA 2023-07: 48.14 vs 0). `bullDiv` (772) uses the same pivot logic as the Backtest's `bullishDivergence` (`conditions.ts:140-155`).
- **Prototype parameters (`XPARAM`, line 864)** carry no min or max, send booleans as strings, round step-1 fields silently, ignore values ≤ 0 and still list three parameters the registry refuses (`adr.timeframe`, `rvol.reference_method`, `rvol.include_current_bar`).
- **PROPOSED.** The Screener calls `F[key]` through the registry and never ports `XI` or the legacy helpers.


## REUSABLE BACKTEST COMPONENTS

Approval item 5: the Backtest calculation reuse matrix.

**Scope and base.** The audit read the repository at `3db84ae` on 2026-10-27. Re-checked at `main` `010af1e` (merge `9390032`): EXEC-BACKTEST-LOAD and EXEC-BACKTEST-SPIN changed terminal-api (`GET /state`), the backtest worker's catalog, server and terminal client, the Backtest page's loading (a shared rack loader, files decoded in a Web Worker, the page drawn before the catalog answers) and the edge-bff store (a connection pool). The references below are updated to `010af1e` (FACT: `git diff --stat 9db630b..010af1e`, 45 files).

**Labels.**
- FACT: seen in code, data or a recorded measurement.
- INFERENCE: a conclusion drawn from facts.
- PROPOSED: a recommendation for the design.
- UNKNOWN: could not be checked.

**Evidence.** Evidence notation as in the header: `audit/<area>.md` and `audit/verify_<area>.json` (reports and verifications; a verification overrides its audit where they differ), `evidence/<area>/<file>` (raw outputs), all relative to `verification/screener/`; repository `path:line` citations are at `main` `010af1e`.

**User context.** FACT: the user's follow-up of 2026-10-27 (brief, verbatim) says Backtest indicators can be added later: *"Tidak perlu terlalu memperhatikan backtesting karena nanti indikator di backtesting bisa kita tambahkan apabila ternyata indikator di screener ini lebih banyak."* A Send-to-Backtest loss listed below may therefore close later, when the Backtest gains operators.

---

### 5.1 Summary

| # | Statement | Label | Evidence |
|---|---|---|---|
| 1 | One formula module is already shared by the Terminal chart, the Backtest page and the backtest worker: `apps/edge-bff/terminal/src/calc/indicators.ts` `F`, with 53 keys. Parameters go through `backtest/src/core/registry.ts` `resolveParams`. 0/1 condition series come from `core/conditions.ts` `Calc` and `conditionSeries`. These are pure modules with no DOM and no Node API. | FACT | registry.ts:1-7; conditions.ts:1-15; api/compute.ts:1-10; the audit ran them unchanged under `node --experimental-strip-types` (node v22.22.0), `evidence/reuse/scripts/*.mts` |
| 2 | `F` equals stored Feature 04 across the market: 844 tickers, 114,544 rows, 15 columns, 0 null mismatches, max relative difference 1.25e-15. | FACT | `evidence/verify_matrix_a/v_market.txt`; see TEST EVIDENCE |
| 3 | The existing loading path cannot screen the whole market. It caps every portfolio and preview at 12 stocks, asks one `/bundle` per ticker, and `/v1/signals` returns only `entry_signals` and `last_signal` per ticker. | FACT | engine.ts:151; load.ts:104-128; contract.ts:308-313; signals.ts:242-245 |
| 4 | The core has no screener semantics: no `between`, no per-condition "within N", no event date or sessions-ago output, no cross-indicator or lagged comparison, no near-miss distance. | FACT | conditions.ts:25, 91-101, 249, 269-292 |
| 5 | Send to Backtest has no landing place. The Backtest page has no import entry and no wire-to-card conversion. | FACT | grep for `location.hash`, `#import`, `import=`, `sessionStorage` in `apps/edge-bff/backtest/src`: no hit (re-run at `010af1e`); app.ts:37-62; request.ts:24-52 |
| 6 | Lowest shared layer: keep the pure core as it is and add one pure screen evaluator beside it. Where that module lives is constrained by the registry hash and `engine_version` (section 5.3). | PROPOSED | section 5.3 |

---

### 5.2 Reuse matrix

Column "Screener use" takes one of three values:
- **As is**: usable without code change.
- **With change**: usable after a change or an extraction. "(pattern)" means the code is a template, not a callable dependency.
- **Not needed**.

Unless a row says otherwise, line numbers and symbols come from the reuse audit (`audit/reuse.md` section 1). They were spot-checked at `3db84ae` and re-read at `010af1e` for every file EXEC-BACKTEST-LOAD or EXEC-BACKTEST-SPIN changed.

#### 5.2.1 Pure core, shared by browser and Node (`apps/edge-bff/terminal/src/calc`, `apps/edge-bff/backtest/src/core`)

| Component | file:symbol | What it does | Screener use | Why (label) |
|---|---|---|---|---|
| Indicator formulas | `terminal/src/calc/indicators.ts` `F`, `DEFAULTS`, `def`, `sma`, `ema`, `rma`, `isN` | The 53 registry indicators I01-I53. Each returns `{output: (number\|null)[]}` aligned with the bars. A non-finite needed input breaks the series. | **As is** | FACT: the only verified formula source. It equals stored Feature 04 market-wide and equals TA-Lib 0.6.8 builds (TEST EVIDENCE T1, T2). FACT: the prototype has two engines of its own, `XI` (lines 866-968) and the legacy helper set (lines 753-777), and both differ from `F` in places (`audit/html_model.md` section 3; `audit/verify_matrix_a.json` additional findings). Neither may be ported. FACT: any byte change to this file changes `registry_version`, and the worker then exits at start with `registry_mismatch` until `backtest-registry.json` is rebuilt (backtest-worker `server.ts:349`; `version.ts` `checkRegistry`). |
| Display registry | `terminal/src/data/indRegistry.json` | Per indicator: zone (12 overlay, 39 panel, 2 volume), units, guides, colours. | **As is** for preview rendering | FACT: it says which outputs sit on the price pane. The same registry-hash rule as `indicators.ts` applies (`version.ts` header). |
| Parameter contract | `core/registry.ts` `REGISTRY`, `BY_ID`, `indicator`, `resolveParams`, `calculate`; `core/backtest-registry.json` | Checks a condition's parameters (unknown key, type, min/max, enum). Fills defaults. Never clamps. | **As is**, with caveats the screener UI must handle | FACT: 67 integer parameters have `min: 1` and no maximum. `std_dev` has max 50 on I27-I29 (`audit/verify_matrix_a.json` a-cost-long-length). FACT: `annualization_periods` is typed `number`, but `def()` floors it, so 252.9 runs as 252 (`audit/verify_matrix_b.json` b-annualization-floor; indicators.ts:239, 249; ERRORS M258). FACT: Supertrend `factor` min 0 is allowed; at factor 0 BBRI flips 1,128 times in 2,115 bars, so the screener should require factor > 0 (`audit/verify_matrix_a.json` I09; `evidence/verify_matrix_a/v_st0.txt`; ERRORS M257). FACT: the I37 `not_accepted` entry contradicts `F.rvol` (section 5.7; ERRORS M256). |
| Per-ticker memo | `core/conditions.ts` `Calc` (l.31) | Memo of indicator outputs per key and parameters, and of flow series. | **As is** | FACT: a screen evaluates several conditions on one ticker. |
| Comparison rules | `core/conditions.ts` `compare` (l.52), `indicatorCondition`, `conditionSeries` (l.249) | Operators gt, lt, crosses_above, crosses_below. Bar 0 is never true. NaN gives false. A cross needs both sides on the previous bar. | **As is** for STATE and EVENT on these 4 operators. **With change** for the rest. | FACT: `OPS` has only 4 operators (conditions.ts:25). lhs and rhs come from one indicator instance with one parameter set (conditions.ts:91-101). Section 5.4 lists the gaps. |
| Price-action conditions | `core/conditions.ts` `PRICE_ACTION`, `priceActionCondition`, `bullishDivergence` | dip; breakout (close > highest high of the previous N bars); volspike (V ÷ SMA(V,N) of the previous bar); macross (SMA only: golden_cross, fast_above_slow); macd (bullish_divergence, crosses_above_signal, histogram_positive). | **As is** for these types | FACT: `breakout` is the working prior-bar Donchian form (conditions.ts:126, 170-172). The generic Donchian condition with a price lhs can never fire: 0 hits market-wide (section 5.4; ERRORS M255). FACT: the prototype's `bdiv` uses the same pivot and divergence logic (`audit/verify_matrix_a.json` additional findings). There is no death cross, no breakdown below the prior N-day low and no EMA-type MA cross. |
| Flow conditions | `core/conditions.ts` `flowCondition`, `flowConditionShape`; `core/flow.ts` `flowData` (l.41), `brokerNet` (l.82), `rollingSum` (l.93), `top5Accumulation` (l.108) | fnet gt/lt, broker gt, top5 gt over N bars, in IDR, computed from one ticker's broker files. | **As is** for a one-ticker preview and for ≤ 12 tickers. **Not needed** for a full-market screen. | FACT: these read per-ticker broker files. Feature_05 holds 46.2 M rows (pg_class.reltuples), above `BACKTEST_MAX_BROKER_ROWS` 20,000,000. FACT: they use all boards and the price-bar calendar (flow.ts:8-14). A Regular-default screener gives different values: on the 20-day foreign net, 168 of 841 stocks differ and 20 flip sign (`audit/verify_flow.json` C11). |
| Entry combination | `core/conditions.ts` `combineEntry` (l.269), `combineExit`, `entryNeed` (l.263), `WINDOW_BARS` | Backtest "within window" rule: one window of 1-20 bars for all conditions, states included. | **Not needed** for matching; `entryNeed` **as is** | FACT: `entryNeed(logic, at_least, count)` equals the prototype's `needOf` (prototype l.1177). FACT: the screener gives each event its own N and reads states on the evaluation bar only (prototype `evalCond` l.1055-1068). |
| Series helpers | `core/conditions.ts` `switchOns` (l.297), `trueBars` | Switch-on bars; count of true bars. | **As is** for chart markers | FACT: core `signals.ts` uses `switchOns` for entry events (l.112, 222). The Backtest page marks switch-ons with the same rule inline (`s[i] && !s[i−1]`, `src/signals.ts:160-166`), not by calling it. |
| Request-level signals | `core/signals.ts` `activeConditions` (l.30), `requestConditions` (l.52), `tickerSignals` (l.90), `periodSignals` (l.124), `previewRow` (l.242) | Checks a condition list; combines the entry per ticker; finds switch-ons in a period; builds a preview row. | **With change** (pattern) | FACT: `previewRow` returns only `entry_signals` and `last_signal` (signals.ts:242-245). INFERENCE: `runSignals` (load → `Calc` per ticker → leave out → warning) is the template for a screen run. |
| Leave-out rules | `core/signals.ts` `EXCLUDED_CODES` (l.255), `unlessLeftOut` (l.261), `leftOut` (l.279) | A condition with no value on the ticker's bars (`INDICATOR_OUTPUT_EMPTY`, `FLOW_OUTPUT_EMPTY`, `FLOW_UNAVAILABLE`) leaves the ticker out instead of failing the run. | **As is**, to produce "n/a" rows | FACT: the core throws `INDICATOR_OUTPUT_EMPTY` rather than returning false (conditions.ts:107-109). The benchmark hit it for 1 ticker with fewer than 75 bars (`evidence/benchmark/results/run_all.log`). |
| Ranking and liquidity | `core/signals.ts` `rankScores` (l.150), `liquidity` (l.174), `LIQUIDITY_BARS` (l.146) | Ranking scores; liquidity = SMA20(close × volume). | **As is** for sort keys and the ADV filter | FACT: the prototype's `adv` uses the same definition (`val = c×v`, prototype l.697; `SMA(val,20)/1e9`). Whether ADV should instead be the exact traded value is a product decision (APPENDIX B, section B.9). |
| Date utilities | `core/signals.ts` `isIsoDate`, `byTicker`, `barMap`, `resultCalendar`, `track` | Dates and bar maps. | **As is** | — |
| Published-file decoding | `core/datafile.ts` `decodeColumnar` (l.67), `inflateVerified` (l.91), `priceSeries` (l.139), `brokerRows` (l.183), `brokerGaps` (l.216), `corporateActions` (l.241), `asOf` (l.259), `dataVersion` (l.271) | gunzip with a size cap; sha256 and size check against the manifest; price, broker and corporate-action decoding; as-of alignment; data version. | **As is** | FACT: `priceSeries` drops a row without four finite prices instead of breaking the series (datafile.ts:158). FACT: parity with the Backtest needs this same loader as well as the same `F` (`audit/verify_matrix_b.json` uncertain b-snapshot-recommendation). |
| Backtest engine | `core/engine.ts` `prepare`, `run`, `validateRun`, `portfolioTickers`, `MAX_PORTFOLIO_TICKERS` (l.151), `LEVEL_LINES` | Event clock and trades. | **Not needed**, except `portfolioTickers` and `MAX_PORTFOLIO_TICKERS` to check a Send-to-Backtest set | FACT: the brief forbids calling the full simulator to calculate indicators. |
| Card ↔ wire mapping | `core/catalog.ts` `LEGACY` (l.41), `legacyCard` (l.64), `legacyToCondition` (l.93), `regToCondition` (l.131), `DISPLAY` (l.13) | Page card (legacy or registry) → wire condition; display scales (Rp B → IDR, % → fraction). | **As is** for Send to Backtest | FACT: the conversion goes one way only. No wire → card function exists (`audit/edge_conventions.md` 4.1). |
| Wire types | `core/contract.ts` `BacktestRequest`, `SignalsPreviewRequest`, `Catalog`, `Limits`, `ApiError` | Request, preview, catalog, limits and error types. | **As is** | — |

#### 5.2.2 Backtest worker (`apps/backtest-worker/src`)

| Component | file:symbol | What it does | Screener use | Why (label) |
|---|---|---|---|---|
| terminal-api client | `terminal.ts` `TerminalClient.bundle` (429), `usable` (463), `cached` (470), `file` (479), `loadTicker` (525), `manifest` (575), `publication` (595), `reference` (607-609), `MemoryCache` (196), `DiskCache` (244) | `/bundle` (`packs: true`), `/manifest`, `/state`, `/reference`; presigned download; sha check; retries; file-origin allow-list; memory LRU and shared disk LRU. | **With change** | FACT: it can load one ticker in a Node service. It has no method for a cross-sectional file. `/manifest` carries no `packs` (terminal-api main.py:307-314). |
| Market loader | `load.ts` `loadMarket` (104), `PlannedClient`, `brokerDataThrough` (188) | Step 1 calls one `/bundle` per ticker whatever the cache holds (load.ts:116). Then it checks the limits and downloads. It re-asks an answer that is too old. It checks the broker data-through date. | **With change** | FACT: built for ≤ 12 tickers. INFERENCE: 845 tickers would mean 845-1,690 `/bundle` grants and audit rows per screen (section 5.5). |
| Request checks | `validate.ts` `checkSignalsRequest`, `pickedStocks` (107-113), `checkConditions`, `CONDITION_ID` | Strict field check; condition checks on empty bars; condition id rule. | **With change** (pattern) | FACT: the 12-ticker cap is enforced here (validate.ts:107-113, 206, 229). |
| Run entry points | `run.ts` `runJob` (112), `runSignals` (196), `checkPublished` (103) | Job and preview runs; published-data checks. | **With change** (pattern; `runSignals` is the closest template) | FACT: `runSignals` returns preview rows, not per-condition values. |
| Compute threads | `compute.ts` `ComputeThread`, `packResult` | Exactly 2 long-lived threads (jobs, previews), one task each (server.ts:108). | **With change**: a screen needs its own thread or service | INFERENCE: a screen on the preview thread would queue behind backtest previews and block them. The worker is 1 replica, and its memory budget was sized for 12 stocks (peak 1.31 GB, worker README). |
| HTTP server | `server.ts` `createApp`, `preview`, `callerWatch`, `deadline` | Key header; preview queue (one at a time); deadline; caller watch; 409 BUSY. | **With change** (pattern) | INFERENCE: adding routes touches the worker the Backtest depends on. |
| Configuration | `config.ts` `loadConfig` | Limits from the environment. | **With change** (pattern) | FACT: `BACKTEST_MAX_PORTFOLIO_TICKERS` may only lower the cap of 12 (config.ts:77). |
| Catalog | `catalog.ts` `buildCatalog`, `groupingsOf`, `ByPublication` (58-81) | Tickers with name, type, sector and industry; groupings; IHSG first and last bar; flow data-through. Kept per publication: rebuilt only when terminal-api `/state` `finished_at` changes, checked at most every 60 s; built at start. | **As is** for the universe list and the sector/industry filters; **As is** (pattern) for per-publication caching | FACT: the reference file holds only ticker, name, type, sector and industry (publisher.py:418-431). FACT: every extra column becomes a portfolio-picker grouping (terminal.ts:156, 622-630). FACT: CONTRACT.md:77-83 [D-L3]. INFERENCE: numeric screener attributes need a separate reference file (APPENDIX C, C.9). |

#### 5.2.3 edge-bff, terminal-api, publisher and pages

| Component | file:symbol | What it does | Screener use | Why (label) |
|---|---|---|---|---|
| edge-bff backtest relay | `app/backtest.py` `WorkerClient` (287), `Backtests.ask` (949), `unless_gone` (971), `latest_preview` (1002), `loads` (94), `error_of`, `json_part` | Worker client with key header and 504 TIMEOUT mapping. Relay on the event loop with timeout = `BACKTEST_TIMEOUT_SECONDS` + 30. Cancels when the caller leaves. One preview in flight per owner (`client_order`). JSON guard against NaN, Inf, 1e400 and lone surrogates. Error redaction. gzip pass-through. | **As is** (pattern) for a screener relay | FACT (`audit/edge_conventions.md` 1.4). |
| edge-bff gateway | `app/main.py` `TERMINAL_ROUTES` (34), `forward_terminal` (366), `session` (247), `write` (254), protections (222-245) | Terminal proxy: allow-listed GET `manifest\|reference\|history\|logo` and POST `files\|bundle` (terminal-api's `/state` is not forwarded), httpx timeout 30 s. Session cookie (one DB lookup per request, on a pool of at most 6 connections, `app/store.py:22-51`). CSRF on writes. Same-origin POST. 128 KiB body cap. | **As is** for one-ticker preview data | FACT: each `/bundle` through it costs one edge session DB lookup and one terminal-api quota transaction. FACT: this relay passes terminal-api JSON through without `public_data` redaction (main.py:384-388), unlike the Orc and worker relays (`audit/edge_conventions.md` 5.3; ERRORS M260). |
| terminal-api | `apps/terminal-api/app/main.py` `bundle` (366-367), `grant` (318), `manifest` (307-314), `publication` (`/state`, 297-305), `reference` (270); `quota.py` `check`; `bucket.py` `_fresh`, `state`, `manifest` | `/bundle` writes one audit row per call (`file_count` = files). `/files`. `/manifest` has no quota, no audit row and no packs. `/state` names the publication (`finished_at`, `price_through`, `broker_through`, `broker_behind_sessions`) with no file, quota or audit row. `/reference` returns one file each. Quotas apply. The manifest is cached until `state.json` `finished_at` changes. | **As is** for one ticker. **With change** for the full market. | FACT: grants are per ticker; the presigned-URL TTL defaults to 120 s. |
| Publisher | `apps/terminal-publisher/publisher.py` `publish`, `publish_packs`, `publish_refs`, `window`, `resolve_price_first_year` | Yearly files; a price pack with all years; a broker archive (all but the last 2 years); reference files. | **With change** if a cross-sectional file is chosen | FACT: price is published from the first stored year, 2018-01-02 (publisher.py:321-323, 471-479; live `min(date)`). INFERENCE: `INDICATOR_ALIGNMENT.md` §3.5 ("price from 2021") is outdated. |
| Terminal page data and rack loader | `terminal/src/data/live.ts` `bundle`, `liveData`; `worker.ts` `download`, `priceRows`, `brokerData`; `rack.ts` `fileCache`, `fetchFile`, `CACHE_LIMIT` (15-16, 29, 78) | Bundle → presigned downloads in a Web Worker; IndexedDB cache keyed by sha256 (50 MB LRU); download retries; price rows; broker aggregation. Since EXEC-BACKTEST-LOAD `rack.ts` is shared by the Terminal and the Backtest page. | **As is** for `rack.ts`; **With change** (pattern) for the rest | FACT: `liveData` is shaped for the Terminal page. FACT: `rack.ts` is the module any rack page is meant to reuse (ERRORS EXEC-BACKTEST-LOAD lesson). FACT: the Terminal maps a null volume to 0 (`live.ts:175`), while the core keeps null (`datafile.ts:159`). |
| Terminal chart and panes | `terminal/src/app/chart.ts` `initChart`, `app/indicators.ts` `initIndicators`, `app/context.ts` | Chart, overlays, indicator panes. | **With change** (library use only) | INFERENCE: bound to the Terminal's `Ctx` and DOM ids (chart.ts:6-7). |
| Terminal relative performance | `terminal/src/app/stats.ts` (263-281); `lineChart` (stats.ts:153, local to `initStats`, not exported) | Stock vs IHSG rebased to 100. | **With change** | FACT: same maths as the prototype's `perfCard`. INFERENCE: extracting `lineChart` touches the Terminal. |
| Backtest page preview stack | `backtest/src/api/live.ts` `liveApi` (124: `bars` 162, `priceOf` 138, `flowOf` 147; one `/bundle` per ticker reused for 90 s, 67-78); `api/load.ts` `loadPrice`, `loadFlow` and `api/load.worker.ts`; `api/compute.ts` `Compute` (22: `indicatorOutputs` 44, `conditionSeries` 61); `api/cache.ts` (re-exports `rack.ts` `fileCache`); `src/signals.ts` `initPriceChart` (125), `refreshSignals` (143) | Browser: `/bundle` → (in the page's Web Worker) `inflateVerified` → `priceSeries` → `Compute.conditionSeries` per card; candle chart with switch-on markers. | **With change** (extract the modules, not the page widgets) | FACT: this is already the "chart + markers from the shared core" pattern (section 5.6). INFERENCE: `signals.ts` uses module state `S`, `DATA` and `$('priceChart')`, so it is not a standalone component. |
| Ticker search | `backtest/src/picked.ts` `searchMatches` | Ticker prefix, then name substring. | **As is** | FACT: same semantics as the prototype's global search (`audit/html_ui.md` 5.2). |
| Broker aggregation | `terminal/src/data/brokerAgg.ts` | Terminal broker-activity aggregation; `avgPrice = value / (lots × 100)` (l.25). | **Not needed** for screener v1 | FACT: the formula is the reference for a gross broker VWAP (APPENDIX B, B.1 row 4). |

---

### 5.3 The lowest shared layer

**What exists (FACT).**
- One pure layer serves three consumers:
  - `indicators.ts` `F` + `indRegistry.json` (formulas);
  - `registry.ts` (parameters);
  - `conditions.ts` (0/1 series);
  - `datafile.ts` (decoding);
  - `flow.ts` (broker series).
- The consumers are the Terminal page, the Backtest page (browser) and the backtest worker (Node).
- Evidence: registry.ts:1-7; conditions.ts:1-15; Backtest Dockerfile copies `terminal/src` because the core imports it (`audit/edge_conventions.md` 1.8).

**PROPOSED (from `audit/reuse.md` section 0, item 2).**
1. Keep the pure core unchanged.
2. Add one pure evaluator module (called `screen.ts` here). For each condition at an evaluation bar it returns `{value, pass, event_date, sessions_ago, na}`, plus the met count, the need and the near-miss flag.
3. Let the browser preview, a full-market screen service and any daily precompute call that one module, and later the Backtest.
4. Add new operators and transforms (`between`, lagged self-comparison, indicator of an indicator, cross-instance comparison, % distance) beside `compare`, so the Backtest can adopt them later without a second formula.
5. Do not let the Screener call the Backtest simulator (`engine.ts`) to get indicator values.

**Placement constraints (FACT, then INFERENCE).**

| Fact | Evidence |
|---|---|
| Any byte change to `indicators.ts` or `indRegistry.json` changes `registry_version`. At start the worker recomputes the hash and calls `process.exit(1)` with `registry_mismatch` until `backtest-registry.json` is rebuilt and redeployed. | backtest-worker `src/version.ts:1-42` (`checkRegistry`); `src/server.ts:349`; `audit/verify_matrix_b.json` additional findings |
| `engine_version` is a content hash over every `*.ts` and `*.json` in `apps/edge-bff/backtest/src/core` plus the worker's `src/*.ts`. It enters the request hash and the result metadata. It does not stop the worker. | `version.ts:4-31`; `run.ts:175, 180`; `core/hash.ts:131-132` |
| The edge-bff image's build context is `apps/edge-bff`. | `audit/edge_conventions.md` 1.8 |

INFERENCE from these facts:
- A screener module **inside** `backtest/src/core` changes the Backtest's `engine_version` and request hashes at the next worker build. It does not change any Backtest number.
- A module **outside** `backtest/src/core` and outside `indicators.ts` leaves the Backtest's versions unchanged. The adversarial verifier recommends this placement (`audit/verify_matrix_b.json` additional findings).
- A screener sub-app can import only from inside `apps/edge-bff` (`terminal/src/calc`, `backtest/src/core`), not from `apps/backtest-worker`.

Where the module lives is a design decision. It belongs to TARGET ARCHITECTURE.

**History rule (FACT, measured).** The evaluator must run on the ticker's full published history, from its first price row, to equal the Terminal, the Backtest and Feature 04.
- With only the last 1,000 bars:
  - EMA 200 still differs at the latest bar on 508 of 575 tickers (worst relative 6.2e-4);
  - MACD 50/200/20 differs on 566 of 575 (NFCX −2.85 vs −3.18).
- With 500 bars, EMA 200 is up to 7.7% off (SAPX 312.44 vs 336.37).
- Cumulative levels (OBV, PVT, A/D, NVI, PVI) never converge.
- Evidence: `evidence/verify_matrix_a/v_tail_custom.txt`, `evidence/verify_matrix_b/startdep_report.txt`; details in TEST EVIDENCE T4.

---

### 5.4 What the core lacks for a screener

| Screener need | Core today | Gap | Label and evidence |
|---|---|---|---|
| `between` (prototype: inclusive and order-agnostic, `v >= min && v <= max`) | No such operator; `OPS` = gt, lt, crosses_above, crosses_below | New operator. Two strict conditions are not equivalent: they change the boundary and count twice under ANY / AT LEAST. | FACT: conditions.ts:25; prototype l.1064 |
| Per-condition "within N sessions" for events and level crosses | `combineEntry` applies one `window_bars` (1-20) to the whole entry. A state then counts if true on any bar of the window. | Each event needs its own N (the prototype has no maximum). States and values must be true **on** the evaluation bar. | FACT: conditions.ts:259, 269-292; prototype `evalCond` l.1055-1061 |
| Latest-bar evaluation with a defined as-of bar | `conditionSeries(c, cond, field, last?)` computes up to bar `last`. No rule exists for choosing the evaluation bar. | The screener needs an as-of rule and a staleness flag. | FACT: conditions.ts:249. FACT: 16 tickers have their last bar before 2026-10-27 (ADHI 2026-08-21 … MSIN/TGKA 2026-10-26; `audit/feature04.md` section 8). FACT: no stock has a price row on 2026-09-17 or 2026-09-18, which are real IDX sessions present for IHSG and in broker data, so "sessions ago" counted on a stock's own bars treats 2026-09-16 and 2026-09-21 as adjacent (`audit/verify_feature04.json` F04-06; `evidence/verify_feature04/v21_ihsg_dates.out`, `evidence/verify_feature04/v22_gapdays.out`). |
| Event date and sessions ago | Not returned. Derivable: in the cross series s, take the largest j in [at−N+1, at] with s[j] = 1; `event_date = dates[j]`, `sessions_ago = at − j`. | Return both fields per condition. | FACT, demonstrated on live bars: BBCA "MACD crosses above signal" last on 2026-10-15, 8 sessions ago; PMUI Supertrend flipped up on 2026-07-31, 58 sessions ago (`evidence/reuse/semantics.txt`). FACT: for a level cross, the prototype shows the current value, not the cross date (prototype l.1065; `audit/html_model.md` 4.2). |
| Near miss | `entryNeed` gives the need. Nothing marks "one short". | The prototype's near miss is count-based only: `A.length > 1 && k > 1 && met === k−1`. No numeric distance exists anywhere. A distance such as value − threshold would be new and is a product decision. | FACT: prototype l.1180. FACT: the detail pill uses `met === k−1` without the guard (l.1599), so the two rules disagree (APPENDIX A, A.3). |
| Cross-indicator comparison (EMA20 vs EMA50; close vs another indicator; fast/slow MA of EMA type) | One indicator instance with one parameter set per condition. `macross` is SMA-only (golden_cross, fast_above_slow). | New condition kind | FACT: conditions.ts:91-101 (`outs = c.out(r.key, params)` for both sides); conditions.ts:124, 176-178 |
| Lagged self-comparison ("SMA rising vs 5 sessions ago", "OBV rising over 20", "histogram rising 3 sessions", Donchian prior-session band) | None | New transform | FACT: `audit/reuse.md` 2.2; prototype line shapes `rising`/`crise` (`audit/html_model.md` 2.4) |
| Indicator of an indicator (OBV/PVT/A/D vs EMA 20; NVI/PVI vs EMA 255) | None | New transform. FACT: EMA-based states on cumulative series depend on where history starts. With EMA 255, the state disagrees up to 1,021 bars after a later start (BNBR from 2021). From a 2025 start, ANTM's latest bar disagrees. SMA-based states are start-independent but need a tie rule on flat windows (BNBR: 358 of 358 disagreements are on flat-OBV windows). | `audit/verify_matrix_b.json` b-cumulative-start-dependence; `evidence/verify_matrix_b/derived_state_report.txt` |
| Derived values (% distance of close from a line; % position inside a band) | Only raw outputs. %B exists only for Bollinger (I28, a fraction, not %). | Transforms on top of `calc.out`; no new formula | FACT: `audit/reuse.md` 2.2 |
| Cross-sectional ranks (`rs_rank`, `magicRank`) | None (`asOf` exists for alignment; I17 ROC gives the return) | Needs the whole universe in one evaluation. Population is a product decision. | FACT: prototype l.827, 855 |
| Price-action types not in the core: death cross, breakdown below the prior N-day low, Ichimoku, Bollinger squeeze, 52-week high/low distance | Only breakout up, SMA golden cross and fast_above_slow | New price-action types. Ichimoku is not among the 53. | FACT: `audit/html_model.md` 2.1 |
| Donchian "close above upper" | Upper = MAX(H, n) includes the current bar, so `price gt upper` can never be true | Map to `price_action breakout`, or add a lag | FACT, market-wide through `compare()` over 844 tickers: gt, xa, lt and xb give 0 hits; against prior-bar bands they give 44,557 / 29,041 / 54,652 / 34,294 (`evidence/verify_matrix_a/v_market.txt`; indicators.ts:345-347; ERRORS M255) |
| "n/a" when a series has no value up to the evaluation bar | Throws `INDICATOR_OUTPUT_EMPTY` | Catch per ticker and mark n/a and not passed, as the prototype does (`na:true`, l.1063) | FACT: conditions.ts:107-109; `EXCLUDED_CODES` pattern |

---

### 5.5 Loader limits that block 845 tickers

**Cost of one ticker today (FACT, `audit/reuse.md` 3.1).**

| Path | Requests | Files and bytes (gzip) | Quota and audit |
|---|---|---|---|
| Price only: `/bundle {datasets:['price'], packs:true}` | 1 `/bundle` + 1 presigned GET | 1 price pack. Rebuilt for all 845 tickers: median 17.2 KB, p90 25.6 KB, max 42.3 KB (BRPT) (`evidence/benchmark/results/packsize.json`) | 1 audit row (`dataset='bundle'`, `file_count`) (terminal-api main.py:318-338, 385) |
| Price + broker (+ events) | 1 + 4-5 | Price pack + broker archive + 2 yearly broker files. The 12 largest stocks together: 28.4 MB and 2,494,454 rows (CONTRACT §3). BBRI archive: 2.2 MB gzip / 14.5 MB inflated. | 1 row, `file_count` 4-5 |
| From the browser (Terminal or Backtest page) | Each call goes through edge-bff | Same files | + 1 edge session DB lookup per call (main.py:247-251) |
| Worker job or preview | + 2 reference grants per call (CONTRACT §8) | Same files | `/manifest` has no quota and no audit row |

**Every limit that blocks a full-market load.**

| Limit | Value | Where | Effect for 845 tickers | Label |
|---|---|---|---|---|
| `MAX_PORTFOLIO_TICKERS` / `BACKTEST_MAX_PORTFOLIO_TICKERS` | 12; the variable may only lower it | engine.ts:151; config.ts:77; validate.ts:107-113, 206, 229 | `/v1/signals` and jobs refuse more with `INVALID_PORTFOLIO` | FACT |
| `/v1/signals` answer shape | `entry_signals`, `last_signal` per ticker | contract.ts:308-313; signals.ts:242-245 | No per-condition value, state, event date or sessions ago | FACT |
| One `/bundle` per ticker before any download | Always, whatever the cache holds | load.ts:116 | 845 grants minimum per screen | FACT |
| Presigned-URL TTL vs worker margin | TTL 120 s; an answer is used only while `age + 60 s < 120 s` | migration `20261025_100` l.79; terminal.ts:463-465; load.ts:146-147 | A large load re-asks grants unless every file is cached: 845 to about 1,690 grants (INFERENCE) | FACT / INFERENCE |
| terminal-api default quotas | `files_per_hour` 60, `tickers_per_hour` 30, `tickers_per_day` 150, `megabytes_per_day` 300 | migration `20261025_100_create_terminal_schema.sql` l.79-84 | A per-ticker full screen is impossible under the defaults | FACT |
| Gateway account override | 1,000,000,000 on all five quotas, marked **TEMPORARY** | DATABASE_CHANGELOG 2026-10-26 | Live value UNKNOWN: pgweb has no permission on schema `terminal` | FACT / UNKNOWN |
| Shared quota account | The worker's `TERMINAL_PROXY_KEY` is `${{terminal-api.TERMINAL_PROXY_KEY}}` | RAILWAY_CHANGELOG (about l.4697) | Worker and browser draw on one gateway account | FACT |
| `access_log` growth | One audit row per `/bundle`. The quota check sums the subscriber's last day on every request (store.py `usage`; index `(subscriber_id, at DESC)`). Rows are kept 90 days. | terminal-api | INFERENCE: 845-1,690 rows per screen, and the per-request quota query grows with daily volume | FACT / INFERENCE |
| `BACKTEST_MAX_BROKER_ROWS` | 20,000,000 (dev) | load.ts `within` | A full-market flow load is refused (F05 holds 46.2 M rows) | FACT |
| `BACKTEST_MAX_DOWNLOAD_BYTES` | 1.5e9 (dev) | load.ts `within` | Price only (~14-16.5 MB) fits. With broker files (≥ 300 MB) it fits in bytes, but memory is the issue: the 12-stock worst case peaked at 1.31 GB (worker README). | FACT |
| Preview concurrency | 1 preview at a time per worker (queue); 1 job (409 BUSY); 2 threads; 1 replica | server.ts:108, 197-235; RAILWAY_CHANGELOG 2026-10-27 | Screens would serialise behind previews | FACT |
| edge-bff preview rule | 1 preview in flight per owner; latest wins (409 `PREVIEW_REPLACED`) | backtest.py:1002 | — | FACT |
| `BACKTEST_MAX_CONDITIONS` | 32 enabled per list | validate.ts `withinConditions` | — | FACT |
| edge-bff POST body cap | 131,072 bytes | main.py:228-234 | 845 tickers ≈ 6 KB: fits | FACT |
| Browser IndexedDB cache | 50,000,000 B, shared by the Terminal and the Backtest page | `terminal/src/data/rack.ts:15-16` (one module since EXEC-BACKTEST-LOAD; `worker.ts:8, 30` and backtest `api/cache.ts:6` use it) | All price packs (14.22 MB rebuilt) fit | FACT |
| Per-object bucket latency | about 0.8 s per object over HTTP/1.1 (ERRORS M240); 5 objects in 0.94-1.16 s with 6 connections | ERRORS_AND_SOLUTIONS EXEC-TERMINAL-SPEED | INFERENCE: a cold browser load of 845 objects takes minutes | FACT / INFERENCE |
| Publisher overwrite window | Files overwritten under the same key during publisher runs (00:00-01:00 and 12:00-13:05 UTC) give `DATA_INTEGRITY` | ERRORS M250 (OPEN) | INFERENCE: a long full-market load is more likely to cross a publish | FACT / INFERENCE |

**Cache layers that exist (FACT, `audit/reuse.md` 3.3).**
- Browser: IndexedDB `terminal-files`, 50 MB LRU by sha256.
- Worker memory: `BACKTEST_CACHE_BYTES` (1.5e9 in dev) per thread.
- Worker disk: `/tmp/backtest-cache`, 1 GiB, shared by the threads (the dev setting, `apps/backtest-worker/README.md:211`). Measured: a 12-stock preview downloaded 48 files (28.27 MB). The job after it read them from disk in 4.7 s, against 7.05-7.23 s cold.
- terminal-api manifests: in memory until `state.json` `finished_at` changes, checked every 60 s, at most 4,000 entries.
- backtest-worker catalog and reference lists: kept per publication (`ByPublication`, catalog.ts:58-81; CONTRACT.md:77-83 [D-L3]).
- edge-bff catalog: 60 s.
- Per run: the `Calc` memo.
- There is **no cache of computed indicator values across requests**.

**Load options for the full market.** These are audit input, labelled PROPOSED or INFERENCE. The choice belongs to TARGET ARCHITECTURE; measured costs are in PERFORMANCE EVIDENCE.

| Option | Requests per screen | Main fact | Label |
|---|---|---|---|
| A. Worker-style per ticker, with the cap lifted | 845 `/bundle` (+ re-asks) and 845 GETs cold | Shares the process the Backtest depends on; 845-1,690 audit rows per screen | INFERENCE |
| B. Browser per ticker (Backtest page pattern) | 845 `/bundle` via edge-bff + 845 GETs | 845 session lookups and quota transactions; minutes cold | INFERENCE |
| C. A published cross-sectional full-history price file | 1 grant + 1 GET | Rebuilt packs total 14.22 MB gzip; decoding all 845 takes 2.8-3.3 s wall (2.9-3.4 s CPU). It needs publisher and terminal-api changes. | FACT (sizes, decode) / PROPOSED |
| D. A long-lived in-memory cache in a service, refreshed on publish | 0 per screen | INFERENCE: about 100-200 MB RAM; pairs with C | INFERENCE |
| E. Read PostgreSQL directly | 1 query | FACT: `edge_bff_runtime` / `edge_bff_login` have no SELECT on Price, F04 or F05 (live `has_table_privilege`). The worker has no DB credentials by design (terminal.ts:1-3). FACT: a full price read takes 1.4-3.0 s server-side. A role or grant change is not approved. | FACT / PROPOSED |
| F. Daily precompute of the 53 defaults | Once per publish | FACT: all 53 defaults over the full universe take 8.1-10.2 s single-thread. Custom parameters still need on-demand compute. | FACT / PROPOSED |

---

### 5.6 Preview-chart reuse

**The Backtest page already runs the preview chain (FACT).**
1. `liveApi().bars(ticker)` (api/live.ts:162) calls `POST /api/terminal/v1/bundle {ticker, datasets, packs:true}` through edge-bff, which applies the session, the CSRF token and Origin. One answer per ticker is reused for 90 s (`URL_LIFE_MS`, live.ts:67-78).
2. The page's loading Web Worker (`api/load.worker.ts`, running `api/load.ts`) takes each file from the shared browser cache or downloads the presigned file with retries (`terminal/src/data/rack.ts` `fileCache`, `fetchFile`).
3. In that worker, `inflateVerified` checks sha256 and size against the manifest entry (datafile.ts:91).
4. In that worker, `priceSeries` decodes the bars (datafile.ts:139). Without a Web Worker (the tests) steps 2-4 run on the page.
5. `Compute.put` builds a `Calc` (api/compute.ts:28).
6. `Compute.conditionSeries(ticker, card)` (api/compute.ts:61) returns the 0/1 series per card. `Compute.indicatorOutputs` (api/compute.ts:44) returns overlay lines.
7. The page marks the bars where a series switches on (`s[i] && !s[i−1]`, src/signals.ts:160-166), the rule of core `switchOns` (conditions.ts:297).
8. `initPriceChart` and `refreshSignals` (src/signals.ts:125, 143) draw a `CandlestickSeries` with `createSeriesMarkers` (signals.ts:130-131). Until the ticker's prices are there the chart shows a loading ring (EXEC-BACKTEST-SPIN).
9. Downloaded files are cached in IndexedDB (`terminal/src/data/rack.ts`, re-exported by `api/cache.ts`; 50 MB, shared with the Terminal).

**Chart library (FACT).**
- The Backtest and Terminal `package.json` both pin `lightweight-charts` 5.2.1; the Terminal also pins `lightweight-charts-drawing` 0.6.2.
- The prototype vendors the same 5.2.1 inline (prototype l.553-557, 197 KB).
- INFERENCE: the vendored copy can be dropped in favour of the npm package.

**What the prototype's preview draws (FACT, `audit/html_ui.md` 3.8).**
- Candles for the last 130 sessions.
- One `LineSeries` per overlay output of each active condition. 12 registry overlays: sma, ema, wma, hma, kama, supertrend, donchian, keltner, psar, bollinger, vwma, vwap; plus the legacy `price_ma` line.
- `arrowUp` markers on the event bars of each condition.
- No volume series, no indicator panes, no IHSG.
- The chart is static (`handleScroll:false`, `handleScale:false`).

**Data per preview (FACT).**
- Price only: 1 file, median 17.2 KB, max 42.3 KB.
- IHSG for a "vs IHSG" line: 1 file, 42 KB.
- The preview never needs full-market OHLCV.

**Reuse constraints.**
- FACT: the Terminal maps a null volume to 0 (`terminal/src/data/live.ts:175`), while the core keeps null (`datafile.ts:159`). PROPOSED: use the core path for the preview, so preview values equal the screen and the Backtest.
- FACT: the sub-app CSP allows presigned bucket downloads (`connect-src 'self' https://*.t3.storageapi.dev`, main.py:39-48). EDGE's own page CSP has `connect-src 'self'` only (main.py:244), which would block them.
- FACT (verifier correction): the prototype's `evalCond` collects event markers over the last 130 sessions for **every** evaluated ticker (l.1060, 1066); only `drawChart` draws them, for the selected ticker (l.1614). INFERENCE: a server only needs to compute markers for the selected ticker (`audit/verify_flow.json` row correction "S3 evaluation note").
- FACT: IHSG has 2 dates that no stock has (2026-09-17 and 2026-09-18). A stock-vs-IHSG rebased chart that aligns by bar offset would be off by 2 sessions across that span. Aligning by date with `asOf` keeps the dates right (`audit/verify_feature04.json` additional findings; `datafile.ts` `asOf`).
- FACT: stored prices mix split-adjusted and raw history. Example: PBSA's 1:2 split on 2026-10-14 is not adjusted (close 845 → 384), so its chart and indicators show a level break. ERRORS D22 records this as OPEN at `010af1e`.

---

### 5.7 Send to Backtest: the gap

**The receiving side today (FACT).**
- The Backtest frame always opens `/backtest-app/` with a fixed `src` (`static/index.html:10807`). It boots again each time the tab opens.
- `boot()` (app.ts:37-62) asks the catalog and the shown ticker's prices at once and does not wait for them: it uses the catalog only if it answers within `QUICK_MS` 60 ms (app.ts:34, 50-51), otherwise draws on `PROVISIONAL` and applies the catalog later in `catalogArrived()` (app.ts:67-85). It reads no URL, hash, `sessionStorage` or strategy key (grep at `010af1e`: no hit). It reads only the layout keys `ml.bw` and `ml.panel` (`layout.ts`).
- Page state holds cards (`LegacyCard | RegCard`). `request.ts:24-52` converts cards to the wire. **No wire → card conversion exists.**
- A grep for `location.hash`, `#import`, `import=` or `sessionStorage` in `apps/edge-bff/backtest/src` returns nothing (re-run at `010af1e`).

**The request contract the hand-off must meet (FACT, CONTRACT §3, `core/contract.ts`).**
- `entry {logic: all|any|at_least, at_least ≥ 1, window_bars 1-20, conditions[]}`.
- Condition kinds:
  - `indicator {indicator I01-I53, params (accepted keys only), lhs price|output, op gt|lt|crosses_above|crosses_below, rhs output|value}`;
  - `price_action` (dip, breakout, volspike, macross, macd);
  - `flow` (fnet gt|lt, broker gt, top5 gt; values in IDR).
- Ids match `^[0-9a-z]{1,6}$` and are unique. At most 32 enabled conditions per list.
- `portfolio.tickers`: 1 to the catalog's `limits.max_portfolio_tickers` distinct stocks (12 today; `BACKTEST_MAX_PORTFOLIO_TICKERS` may only lower it; `contract.ts:337-342`, `apps/backtest-worker/src/config.ts:21, 75-82`). `single.ticker`: one stock.
- The page keeps logic `'n'` for `at_least` (state.ts:17-31, request.ts:21-23). `RegCard` accepts ops `gt`, `lt`, `ca`, `cb` only.

**What the prototype sends (FACT).**
- `toBacktest` (l.1655-1673) and `openSend` (l.1674-1693) build `{v:1, source:'EDGE Screener', screen, date, mode, tickers:[{tk, px, vol}], conds:[{type, len/fast/slow/sig/k/smooth/broker, op, val}], logic, atLeast}`.
- Delivery: as `backtest.html#import=<base64>`, as a JSON download, or as a copied link.
- It maps 13 legacy keys, 31 (key, op) pairs, onto the Backtest `LEGACY` types. It maps **none** of the 53 registry indicators (`evidence/html_ui/catalog.json` `toBacktest`).
- `px` and `vol` are synthetic values the Backtest does not use.
- Tickers come from the single pick, else the selection, else all matches. This can exceed 12.

**What maps losslessly (from `audit/reuse.md` section 6, with the verifier's corrections).**

| Screener element | Backtest mapping | Lossless? | Label and evidence |
|---|---|---|---|
| Registry indicator VALUE gt/lt a number (I01-I53) | `RegCard {ind, p, lhs:{t:'out',o}, op:'gt'\|'lt', rhs:{t:'val',v}}` | **Yes**: same `F`, same registry defaults | FACT |
| Level cross "within N" | op `ca`/`cb` + `window_bars = N` | **Yes only if** every event shares one N ≤ 20 and there is no STATE condition | FACT: conditions.ts:269-285 |
| Close above/below a line or band (SMA, EMA, …, VWAP basis; band upper/lower) | lhs price, rhs output | **Yes** (STATE). The Donchian prior-session form maps to `price_action breakout`, up only. | FACT |
| Pair cross or above (MACD, PPO, PVO, TSI, KVO, Stochastic, Stoch RSI, Aroon; +DI vs −DI) | lhs output a, rhs output b | **Yes** | FACT |
| Supertrend or PSAR up / flip | `direction` gt 0 / ca 0 / cb 0 | **Yes** | FACT: direction is 1 or −1 (indicators.ts:329-343) |
| Volume above Vol SMA/EMA | lhs price with `price_input 'volume'` | **Yes** | FACT |
| `between` | Two conditions, gt and lt | **Lossy**: strict vs inclusive, and it counts twice under ANY / AT LEAST | FACT |
| Rising vs N ago; cumulative line vs its EMA; % distance or % band position | No operator | **Lossy** | FACT |
| MA cross of EMA type; death cross; breakdown below the prior low; Ichimoku; squeeze; 52-week distance; RS vs IHSG; RS rank | Only SMA golden cross / fast_above_slow and breakout up | **Lossy** | FACT |
| STATE and EVENT mixed, with N > 1 | One `window_bars` W for all: a state becomes "true on one of the last W bars" | **Lossy** unless W = 1 and every N = 1 | FACT: conditions.ts:269-285 |
| "Match today" | The Backtest trades switch-ons (false → true) of the combined state | INFERENCE: consistent in concept; a 10-day match is one entry | INFERENCE |
| Flow: fnet, single-broker net | `fnet` / `broker` (value × 1e9) | **The values map; at the decided board the formula is the same.** The Backtest uses all boards and the price-bar calendar, which skips a broker row on a date without a price bar (flow.ts:6-7), so a Nego-only day changes the value (81 stock-days of 15 stocks in 20 sessions; FLOW INDICATOR PROPOSALS 16.10). FACT: a Regular-board value differs (168 of 841 stocks on the 20-day foreign net, 20 flip sign). With all boards as the Screener's default (P8, decided 2026-10-28) the board matches; only the Regular variant is lossy, and the calendar is P20 (b). | FACT: flow.ts:8-14; `audit/verify_flow.json` additional findings and C11 |
| Flow: top-N broker net | `top5` (top 5 fixed, IDR) | **Lossy** when N ≠ 5. FACT: the prototype sends `topacc` as `top5` whatever its `top` parameter, so top = 3 silently runs as top 5. | prototype l.1669; flow.ts:108-119; `audit/verify_flow.json` row correction S3 row 2 |
| Flow: bandar status acc / bigacc / gt | Prototype maps all three to `top5 > 0` | **Lossy**: the ratio, the thresholds and N are dropped | prototype l.1670; `audit/verify_flow.json` row correction S3 row 1 |
| Flow: bandar ratio thresholds, foreign % of value, streaks, frequency spike, bandar average price, silent accumulation | No Backtest type | **Lossy** (screen only) | FACT |
| Broker default | Backtest default broker is YU (`backtest/src/core/catalog.ts:54`); the prototype's Broker Follow preset uses YP (l.1089) | One default must be chosen (P20 a) | FACT (`audit/verify_flow.json` additional findings) |
| Fundamentals | No data in the DB | **Screen only** | FACT |
| Universe filters (index, board, cap, price, free float, notation) | Only ADV ↔ `portfolio.min_avg_value_20d_idr` (same SMA20(c×v)), applied per signal day, not at the evaluation date | **Lossy** | FACT |
| More matches than the catalog's `max_portfolio_tickers` (12 today) | The user must pick at most that many (P13) | **Lossy**. The Backtest also warns `SURVIVORSHIP` (engine.ts:536). | FACT |
| Period, exits, costs, sizing | Not part of a screen | The Backtest page uses its defaults (state.ts:34-43) | FACT |
| RVOL `include_current_bar` (I37) | `regToCondition` drops the parameter when it equals the workbook default `false` | **Mislabelled**. The registry lists `include_current_bar: False` as `not_accepted`, "the value the module implements" (build-registry.mjs:37; catalog.ts:128-139). But `F.rvol` divides by `sma(V,n)[i]`, which includes the current bar (indicators.ts:484; INDICATOR_SPEC I37; user decision 2026-10-25, EXEC.md:7881). The prototype sends the string `'false'`, which `regToCondition` refuses with `PARAM_NOT_ACCEPTED`. | FACT; recorded as ERRORS M256 (2026-10-28); the Screener keeps the parameter hidden (P6, decided with the go) |
| Legacy `stoch` %D; `price_ma`/`ma_cross` of EMA type | Not mapped by the prototype (only SMA versions map; %D dropped) | **Lossy** | FACT (`audit/html_ui.md` 3.10) |

**Hand-off options (PROPOSED, `audit/edge_conventions.md` 4.2; the one-shot key is the one chosen in TARGET ARCHITECTURE §6.15 and FRONTEND INTEGRATION 9.4).**
- **One-shot `sessionStorage` key.** The Screener frame writes a key such as `edge-backtest-import`, holding page-shaped cards (`RegCard` / `LegacyCard`), logic, `atLeast`, window, mode, tickers (at most the Backtest catalog's `limits.max_portfolio_tickers`, which the Screener reads from `GET /api/v1/backtests/catalog`, 12 today; never a number typed in the Screener) and a `left_out` list with reasons. It then asks the shell to navigate to `/backtest` through a same-origin `postMessage`. The Backtest page reads and deletes the key once, at the start of `boot()` (app.ts:37), and applies it once the catalog is known, on either path: in `boot()` when the catalog answers within `QUICK_MS` (app.ts:34, 50-51), or in `catalogArrived()` (app.ts:67-85). It validates against the arrived catalog's `limits`, never `PROVISIONAL`, through `toWire` / `regToCondition` and `portfolioTickers`.
  - Precedent: `edge-side-attach:<id>` (index.html:10951, 10973; Chromium test `tests/test_ask_branch.py:70-84`).
- **Alternatives:** a URL hash (the prototype's approach; the payload lands in browser history), `postMessage` carrying the data (the shell must buffer it), or a server-side draft (a new table for a single-owner action).
- **Coordination (FACT):** EXEC-BACKTEST-LOAD has landed on `main` (EXEC.md:8444-8462; CONTRACT.md:77-83) and rewrote the Backtest `boot()`; a Phase 1b import must hook both catalog paths, not "after `applyCatalog` and before `load`". Two sessions editing `apps/edge-bff/backtest` caused the M248 overwrites before.


## TARGET ARCHITECTURE

Approval items 6 (current vs desired data flow) and 7 (recommended target architecture). Everything in this section is **PROPOSED** unless a line carries another label; **DECIDED** marks a product decision the user took on 2026-10-28 (UNKNOWNS / PRODUCT DECISIONS 13.2). The user gave the "go" the same day (`EXEC.md` EXEC-SCREENER): Phase 1 is in execution on dev, phase by phase, and each element below is claimed only when it is verified live (AGENTS.md). The audit itself changed nothing in the repository, the database or Railway.

Evidence notation (as in the header): `audit/<area>.md §n` is an audit report and `audit/verify_<area>.json` its adversarial verification (the verification wins where it refutes the audit); `evidence/<area>/<file>` is raw evidence; all are relative to `verification/screener/`. A file named as "local, not committed" was read during the audit but is not in the repository. Repository citations are `path:line` at `main` `010af1e`. The audit first read the code at `9db630b` (the same code as `641e55e`); while it ran, EXEC-BACKTEST-LOAD and EXEC-BACKTEST-SPIN landed on main (`9db630b..010af1e`), and the files they changed were re-read on 2026-10-28 at `010af1e`; every other cited file is identical at both commits (`git diff --name-only 9db630b 010af1e`). The re-read files: terminal-api `main.py` and `bucket.py` (`GET /state`), backtest-worker `terminal.ts`, `catalog.ts` and `server.ts`, the Backtest page `app.ts`, `terminal/src/data/rack.ts`, `terminal/src/ui/spin.ts`, edge-bff `main.py` and `store.py` (connection pool), `CONTRACT.md` [D-L3] and `BACKTEST_END_TO_END.md` §17. Sections 6.2, 6.5, 6.15, 6.17 and 6.18 depend on them.

**Live checks.** Read-only statements through pgweb, run on 2026-10-27 at about 21:00 UTC and re-run on 2026-10-28 with the same results (L6 on 2026-10-28 only). Cited below as "live L*n*".

| ID | Statement | Result |
|---|---|---|
| L1 | `has_table_privilege('terminal_publisher_login', 'public."Feature_06_Foreign_Domestic"' and `'public."Feature_04_Technical_Indicator"', 'SELECT')` | false, false |
| L2 | `pg_has_role('terminal_api_login' and 'terminal_publisher_login', 'terminal_market_reader', 'MEMBER')` | true, true |
| L3 | `has_table_privilege('edge_bff_runtime', c.oid, 'SELECT')` over every table and view of schema `public` | 0 of 87 |
| L4 | `SELECT count(*) FROM public."Table_Catalog"` | 84 |
| L5 | per date: `count(DISTINCT ticker)` of F06 Regular rows and of F05 (`Feature_05_Foreign_Domestic_Broker_Detail`) Regular rows | 865 = 865 (2026-10-27), 862 = 862 (2026-10-23), 859 = 859 (2026-10-01), 0 = 0 (2026-10-24, a Saturday) |
| L6 | `idx_event_annotation`, family `CORPORATE_ACTION`, type in `PRICE_ACTION_TYPES`, annotation date ≥ 2026-09-12; closes across each ex-date from `Price_Stock_Indonesia_IDX` | 8 with ex-date ≤ 2026-10-27: FORU 2026-09-22 (close 2,560 → 176), BAJA 09-28, ENRG 10-05 (1,440 → 1,030), VKTR 10-07 (835 → 670), BRNA 10-09, AHAP 10-09, PBSA 10-14 (845 → 384), BUVA 10-14; 5 dated later: MGLV 11-02, PPGL 11-03, CBRE 11-03, BMAS 11-24, PRDA 12-18. RAJA (split 2026-07-16, before the boundary) closes 920 → 875: adjusted |
| L7 | `count(DISTINCT "Sector")`, `count(DISTINCT "Industry")` of `IDX_Stock_Universe` | 12 and 59 values, each including `Undefined` (4 rows: IHSG, XCID, XCIS, XSPI) |

Labels: **FACT** (cited), **INFERENCE** (reasoned from facts), **PROPOSED** (a design choice), **UNKNOWN** (not established).

Each major proposal ends with a card: the need, the class of problem, the fix and the layer that owns it, what it covers and does not, risk and cost, how it is verified, and whether it is permanent or TEMPORARY.

### 6.1 Design invariants

| # | Invariant | How it is enforced |
|---|---|---|
| I1 | **One formula path.** Every technical number is `F[key]` through `Calc.out(key, resolveParams(...))`. There is no SQL, TA-Lib or prototype `XI` copy. | Screener core imports `indicators.ts`, `registry.ts`, `conditions.ts`; a test fails if a screener file defines an indicator kernel |
| I2 | **One bar snapshot per screen**, from the same rack publication the Terminal and Backtest read | Every response carries `price_data_version` and `published_at` |
| I3 | **Backtest untouched.** No byte change in `indicators.ts`, `indRegistry.json`, `backtest-registry.json`, `backtest/src/core/**` or `apps/backtest-worker/**` | Tripwire `scripts/screener/check_backtest_untouched.mjs` (`engineVersion()` and `REGISTRY_VERSION` equal those of `origin/main`) |
| I4 | **Feature 04 unchanged.** It is a parity oracle only | Tripwire covers `features/feature04/**`, `apps/feature-04-worker/**`; no migration touches its tables |
| I5 | **Nothing fabricated.** Every cell is PASS, FAIL or NA, and every NA carries a reason code | Contract type; a test asserts no `null` value without a reason |
| I6 | **Versions in every response** | `versions{}` and `data{}` blocks (API CONTRACT §8.3) |
| I7 | **No silent adjustment.** Invalid input is refused with the field and the fix; it is never clamped, rounded or reordered | `validate.ts`; refusal tests |

### 6.2 Current vs desired data flow (approval item 6)

**Current (FACT).** The prototype computes everything in the browser on synthetic data (`audit/html_ui.md` §1). No screener backend exists. The real market data reaches EDGE pages only per ticker:

```
 idx-price-cron 10:00 UTC                       stockbit-updater (one round per deployment, no schedule)
        |                                                   |
        v                                                   v
 PostgreSQL: Price_Stock_Indonesia_IDX --trigger--> F04 queue --> feature-04-worker --> Feature_04 (AI readers only)
             IDX_Stock_Universe, idx_event_annotation          IDX_Broker_Summary --> F05 --> F02 / F03 / F06
        |  terminal_publisher_login reads Price, F05, IDX_Stock_Universe, IDX_Broker_Profile, idx_event_annotation
        v
 terminal-publisher (cron 07:30 and 19:00 WIB): per-ticker yearly files + packs, manifests, state.json last
        |
        v
 bucket terminal-display (sin)  <------------------- presigned GET (per file) ----------------------+
        ^                                                                                           |
 terminal-api (sfo): /state (no grant) /bundle /files /manifest /reference /history /logo; quotas; 1 audit row per grant
        ^  x-terminal-proxy-key (one gateway subscriber)          ^  x-terminal-proxy-key
        |                                                         |
 backtest-worker (<= 12 tickers; 2 compute threads;       edge-bff gateway /api/terminal/v1 (allow-list, no /state)
   catalog kept per publication via /state)
        ^                                                         ^
        +---- edge-bff /api/v1/backtests (relay) <---- browser: Terminal page, Backtest page (one /bundle per ticker)

 Screener: prototype HTML only; synthetic data and formulas in the browser; nothing above is used.
```

Evidence: `apps/terminal-publisher/publisher.py:17-18, 55-66, 549-554`; `apps/terminal-api/app/main.py:297-445` (main `010af1e`: `/state` at 297-305, the file and history routes after it); `apps/backtest-worker/src/catalog.ts:58-81` (`ByPublication`); `apps/edge-bff/app/main.py:34-36`; `audit/reuse.md` §3; `audit/feature04.md` §7; live L1 (`terminal_publisher_login` cannot SELECT F04 or F06).

**Desired (PROPOSED).**

```
 PostgreSQL: tables unchanged. Phase 2 adds one NOLOGIN read group (SELECT on F06) for terminal_publisher_login only
        |
        v
 terminal-publisher, same 07:30 / 19:00 WIB run (CLI deploy):
   per-ticker files + packs ........................................ unchanged
   ref/tickers.json.gz (name, type, sector, industry) ................................. unchanged, reused
   + v1/xsection/price.<sha16>.json.gz   + v1/xsection/actions.<sha16>.json.gz ....... Phase 1
   + v1/xsection/flow_f06.<sha16>.json.gz + v1/xsection/broker_window.<sha16>.json.gz . Phase 2
   + state.json gains xsection:{name:{key, sha256, bytes, rows, as_of}} (still written last)
        |
        v
 bucket terminal-display (sin)
        ^
 terminal-api: GET /api/terminal/v1/state (exists, EXEC-BACKTEST-LOAD; any subscriber; no quota, no audit row)
                 + its answer gains the xsection index (one field added to STATE_FIELDS)
               + POST /api/terminal/v1/xsection {names} (new; proxy key only; 1 audit row; file quota = n)
        ^  private network, x-terminal-proxy-key
 screener-worker (new; sfo; private; no DB or bucket credentials):
   poll /state every 60 s -> on a new finished_at: grant only the files not cached by sha256, download,
   verify sha256 and size, decode, cross-check, compute the 53 defaults with F over full history,
   swap the snapshot all-or-nothing
   /v1/catalog /v1/universe /v1/run /v1/preview /v1/validate /v1/counts   (x-screener-worker-key)
        ^  private network
 edge-bff app/screener.py: /api/v1/screener/* (session cookie, Origin + CSRF on writes, relay, latest wins)
        + edge_bff.screener_items, edge_bff.watchlist_items (Phase 1 migration, P12)
        ^  same origin
 browser: /screener frame (screener-app; renders only; no formula code; connect-src 'self')
        |  Send to Backtest: one-shot sessionStorage key + postMessage navigation (Phase 1b)
        v
 /backtest frame: page-only import in boot(); backtest-worker unchanged

 Unchanged: backtest-worker, feature-04-worker, stockbit-updater, feature-01-worker, Feature 04 tables.
 Not reachable from the browser: /state, /xsection (absent from the edge-bff allow-list, main.py:34-36).
```

**What changes, per hop.**

| Hop | Today (FACT) | Desired (PROPOSED) | Why |
|---|---|---|---|
| DB → publisher | One price query per ticker (`PRICE_SQL`, `publisher.py:55-57`) | Plus one whole-universe price statement (about 2.0 s seq scan server-side, `audit/reuse.md` §3.4 E), one corporate-action read of `idx_event_annotation` (the reference file from `IDX_Stock_Universe` is already written today); Phase 2 adds per-date F06 and F05 reads with literal date bounds | One read per publication instead of one per screen |
| Publisher → bucket | Per-ticker files and packs, written under fixed keys (M250) | Plus 2-4 content-addressed xsection objects | Immune to M250 by construction (INFERENCE) |
| terminal-api | `/state` names the publication (`main.py:297-305`, no grant); every file reaches a reader through a per-ticker grant (`main.py:307-445`) | `/state` also answers the `xsection` index; new `POST /xsection` for proxy-key callers | 1 grant per publication instead of 845-1,690 (`audit/benchmark.md` §4) |
| Compute | Browser (prototype); worker capped at 12 tickers (`engine.ts:151`) | `screener-worker`, whole universe in memory | Hard constraint: no full-market OHLCV to the browser |
| Browser | Synthetic data, `XI` formulas | Renders server answers; preview is server-computed | One formula path (I1) |

### 6.3 Components and ownership

| Component | Status | Owns | Deploy |
|---|---|---|---|
| `apps/edge-bff/terminal/src/calc/indicators.ts` `F`, `indRegistry.json` | Unchanged (I3) | The 53 formulas and their display registry | — |
| `apps/edge-bff/backtest/src/core/*` | Unchanged (I3) | Parameter contract, `Calc`, `compare`, patterns, flow helpers, file decoding | — |
| `apps/edge-bff/screener/src/core/*` | New | Screener contract, validation, metrics, transforms, evaluation, match, planner, cross-section, flow metrics, universe filters, presets, the non-indicator metric catalog (`screener-metrics.json`), Backtest translation | Imported by the worker and (two files) by the page |
| `apps/screener-worker` | New service | Snapshot lifecycle, thread pool, private API, refresh integrity | GitHub `main`, Dockerfile, watch patterns (P3) |
| `apps/terminal-publisher` | Changed | xsection files and their index in `state.json` | CLI upload |
| `apps/terminal-api` | Changed | `/state` answer gains `xsection` (`bucket.py:8` `STATE_FIELDS`); new `POST /xsection` | CLI upload |
| `apps/edge-bff/app/screener.py` + store | New module | Public API, auth, relay, saved items | With edge-bff, GitHub `main` |
| `apps/edge-bff/screener/` | New sub-app | The page | With edge-bff (new Dockerfile stage) |
| `apps/edge-bff/backtest/src/{app.ts, import.ts}` | Changed in Phase 1b | Import of a Send-to-Backtest handoff | With edge-bff |
| Feature 04 tables, worker and engine | Unchanged (I4) | Parity oracle in tests | — |

### 6.4 Where screening runs

**Decision (PROPOSED).** A new private service, `screener-worker`: Node 22 with type stripping and the backtest worker's module loader (`apps/backtest-worker/loader/register.mjs`, which resolves the Terminal's extensionless imports, ERRORS M249), no npm runtime dependency, 1 replica in `sfo`, private networking only, no Postgres or bucket credentials. It reads the rack through terminal-api with the gateway proxy key, as backtest-worker does (`apps/edge-bff/backtest/CONTRACT.md` §1). Pure code lives in `apps/edge-bff/screener/src/core/`; edge-bff relays through `app/screener.py`; the browser renders only.

**Options rejected.**

| Option | Verdict | Evidence |
|---|---|---|
| Inside backtest-worker | Rejected | FACT: `engine_version` hashes every file in `backtest/src/core` and the worker's `src` (`apps/backtest-worker/src/version.ts:18-21`) and enters every Backtest request hash (`hash.ts:131-132`); any screener file there would silently change every Backtest result key. FACT: 2 compute threads, one preview at a time, runs capped at 12 tickers (`engine.ts:151`), worst case 1.31 GB peak (`audit/reuse.md` §1.2, §3.2) |
| Inside edge-bff | Rejected | FACT: `uvicorn --workers 1` (`.railway/railway.ts:184`); its runtime role reads no market table (live L3: 0 of 87 public tables); Python cannot run `F` |
| In the browser | Rejected | Breaks the hard constraint; 845 `/bundle` calls; default quotas allow 30 tickers per hour (`audit/benchmark.md` §4) |
| SQL or Python/TA-Lib engine | Rejected | A second formula implementation. FACT: TA-Lib MACD, CMO, STOCHRSI fastk and PPO (default matype) differ from `F` (`audit/matrix_a.md` pattern 3); 42 of 53 indicators have no Feature 04 code (`audit/verify_feature04.json` F04-17) |

**Cost is small (FACT, `audit/benchmark.md` §2, one thread, data in memory).** One custom indicator over the whole universe on full history: 80-250 ms. Three conditions: 354-564 ms. All 53 defaults (76 outputs): 8.1-10.2 s wall (first-repetition CPU 9.6-10.7 s; `evidence/benchmark/results/all53_full.metrics.json` and its two repeats). Peak RSS 299 MB, almost all of it the input bars. Other audits measured the 53 defaults at 11.5 s and about 15 s on other runs (`audit/html_model.md` §3.4; `audit/reuse.md` §0); Phase 17 measures it on the service.

**Threads (PROPOSED).**
- A `worker_threads` pool starting at K = 2; Phase 17 sets K.
- The next snapshot is built on a builder thread while the current version keeps serving.
- Bars move to SharedArrayBuffer-backed `Float64Array` columns only after a bit-parity test of `F` on typed views against plain arrays (53 indicators × 50 tickers). If that test fails, each thread holds its own copy (memory × K).

**Deploy (DECIDED, P3 a, 2026-10-28; the service is created in Phase 1 through the pinned IaC plan, 6.17).** GitHub `main`, root `/`, `dockerfilePath apps/screener-worker/Dockerfile`, watch patterns `/apps/screener-worker/**`, `/apps/edge-bff/screener/src/core/**`, `/apps/edge-bff/backtest/src/core/**`, `/apps/edge-bff/terminal/src/calc/**`, `/apps/edge-bff/terminal/src/data/indRegistry.json`, `/apps/backtest-worker/src/terminal.ts`, `/apps/backtest-worker/loader/**`, `/apps/backtest-worker/scripts/build-registry.mjs`. Precedent: feature-04-worker (`.railway/railway.ts:162-169`). After each merge, check the deployment of the merge commit (ERRORS M252). The last two patterns are a refinement of the draft list: the image needs the loader, and the start-up registry check imports `build-registry.mjs` (`apps/backtest-worker/src/version.ts:38`).

| Card | |
|---|---|
| Need | Whole-universe screens with the shared formulas, without touching the Backtest worker and without sending full-market OHLCV to the browser |
| Class | CPU-bound cross-sectional compute over the rack. Future macro or cross-asset screens add a file family to the same service, not a new service |
| Fix and layer | Service contract (private API) + pure core module |
| Covers | Every screen, preset count and preview |
| Does not cover | AI access to screener values (a later onboarding per `NEW_TABLE_ONBOARDING_PLAN.md`) |
| Risk and cost | One Railway service. Memory INFERENCE 0.5-1 GB, measured in Phase 17. Shared formula changes redeploy it (wanted) |
| Verification | Tripwire (I3); backtest-worker `npm test` and `npm run registry:check` green; load test: screens during a Backtest job leave the job's duration unchanged |
| Permanence | Permanent |

### 6.5 Market data path, data version, freshness and as-of policy

**Decision (DECIDED, P1 a, user 2026-10-28): one source, the rack publication.** How the page and its data load after the browser opens is in PAGE LOAD SEQUENCE. The mechanism below is PROPOSED. A content-addressed cross-sectional file family:
- key `v1/xsection/<name>.<sha16>.json.gz`, never overwritten;
- written by the existing terminal-publisher in the same `daily` run (07:30 and 19:00 WIB, `publisher.py:17-18`, user decision 2026-10-26);
- written before `state.json`, which gains `xsection: {name: {key, sha256, bytes, rows, as_of}}`. FACT (main `010af1e`): `state.json` is read by the publisher itself (`publisher.py:496`) and by terminal-api (`Bucket._fresh` and `Bucket.state()`, `bucket.py:27-53`), which serves `finished_at`, `price_through`, `broker_through` and `broker_behind_sessions` on `/state`; the backtest worker uses `finished_at` and `broker_through` from it (`apps/backtest-worker/src/terminal.ts:595-603`, `catalog.ts:42`). `state()` copies only `STATE_FIELDS` (`bucket.py:8`), so a new key in the file changes none of these readers;
- each publisher mode rebuilds the files whose inputs it changed (`daily`, `backfill` and `packs` rebuild `price` and `actions`; `events` rebuilds `actions`; in Phase 2 `daily`, `backfill` and `broker-range` rebuild the flow files) and carries the other index entries forward; objects no index references are deleted on the run after the next one, so a reader holding the previous index never loses its object.

**terminal-api.** FACT (main `010af1e`): `GET /api/terminal/v1/state` exists since EXEC-BACKTEST-LOAD K1 (terminal-api deployment `689dc465`, SUCCESS 2026-10-27, `RAILWAY_CHANGELOG.md`; `main.py:297-305`). It is `Depends(subscriber)`, so it answers the gateway proxy key or a direct subscriber's session cookie (`main.py:165-179`); it grants no file, writes no audit row and answers 503 `state_unavailable` when `state.json` is unreadable. The backtest worker builds its catalog from it (`ByPublication`, `catalog.ts:58-81`; `CONTRACT.md` [D-L3], lines 77-83).

PROPOSED:
- `/state` gains one additive field: `xsection` joins `STATE_FIELDS` (`bucket.py:8`), and `test_bucket_state_keeps_the_last_read_publication`, which asserts the exact field set, gains it. The backtest worker's `publication()` copies only three fields (`terminal.ts:601`), so it is unaffected. `/state` keeps its current access: the index names object keys and hashes but grants nothing, because the bucket is private and only a grant presigns a key.
- The only new route is `POST /xsection`, accepted only from a proxy-key caller (`x-terminal-proxy-key`, `main.py:26, 149-154`). terminal-api is also public (`terminal-api-dev.up.railway.app`), so a grant route open to any subscriber would let a direct subscriber pull a 14 MB file against the shared quota.
- Alternative considered: leave `/state` unchanged and return the index only from `POST /xsection`. Not chosen: a grant counts the bytes of every named file against `megabytes_per_day` (`main.py:318-327`), so a worker that cannot see the index first must grant, and count, every file at every publication and after every restart, even when its disk cache already holds the file by sha256. With the index on `/state` it grants only the files it lacks.

| Route | Answer | Quota and audit |
|---|---|---|
| `GET /api/terminal/v1/state` (exists) | `finished_at`, `price_through`, `broker_through`, `broker_behind_sessions` (FACT); PROPOSED: plus the `xsection` index | None (FACT, `main.py:297-305`) |
| `POST /api/terminal/v1/xsection {names}` (new) | `finished_at`, then per name a presigned URL, `sha256`, `bytes`, `rows`, `as_of` | 1 audit row under the `REF` pseudo-ticker, as reference files are logged (`main.py:278-280`, `quota.py:5`), so no terminal-schema migration; file quota = number of names; bytes counted |

Neither route is in edge-bff's browser allow-list (`apps/edge-bff/app/main.py:34-36`, FACT at `010af1e`), so the browser can never pull these files.

**Phase 1 files.**

| File | Content | Built from |
|---|---|---|
| `price` | Every ticker including IHSG, full history from `price_first_year`. One columnar document (columns `t,d,o,h,l,c,v`, ordered by ticker then date) plus `tickers: [{t, pack_sha256, first, last, rows}]` | One bounded statement: `PRICE_SQL` without the ticker filter (seq scan of 1.33 M rows, about 2.0 s server-side, `audit/reuse.md` §3.4 E). Alternative: the pack documents of the same run. A publisher unit test asserts that each ticker's slice equals its pack document |
| `actions` | Price-affecting corporate actions (`PRICE_ACTION_TYPES`, `datafile.ts:236`) with an ex-date on or after `ADJUSTED_HISTORY_BOUNDARY` 2026-09-12 (`engine.ts:157`), future ex-dates included, each with `ratio_old` and `ratio_new`; cash dividends of the last 6 years with `amount_per_share`, `currency` and ex-date | `idx_event_annotation` (already readable by the publisher, `scripts/provision_terminal_logins.py:15-17`) |

Name, type, sector and industry are not copied into a new file. FACT: the publisher already writes them to the reference file `ref/tickers.json.gz` from `IDX_Stock_Universe` (`publisher.py:30, 418-431`); the Backtest reads it through `/reference/tickers` (`TerminalClient.reference`, `terminal.ts:607-627`) and derives its groupings with `groupingsOf` (`catalog.ts:20-31`). The worker reads the same file once per new `finished_at`. INFERENCE: it sits under a fixed key (the M250 class), so the worker checks that every ticker of the `price` file is in it and fails the refresh otherwise. First and last bar per ticker come from the `price` file's `tickers` list.

Why one columnar document (FACT): `inflateVerified` checks sha256 and size, then `decodeColumnar` requires a `columns` list of equal-length arrays (`apps/edge-bff/backtest/src/core/datafile.ts:67-96`). The worker slices each ticker into a document of the pack shape and calls `priceSeries` (`datafile.ts:139`), so the Terminal and Backtest row rules apply unchanged (a row without four finite prices is dropped). INFERENCE: the inflated document is about 75-80 MB (65.0 MB of pack JSON plus a ticker column, `audit/benchmark.md` §4), so the worker's inflate cap (`SCREENER_MAX_INFLATED_BYTES`, passed as `TerminalClient`'s `maxFileBytes`, `terminal.ts:74, 493`) must allow it; its value is set from the first measurement (U4, S14; API CONTRACT §8.9).

**Worker refresh rules.**
1. Poll `/state` every 60 s. Act only when `finished_at` changes, and never while a refresh is already running. FACT: `TerminalClient.publication()` (`terminal.ts:595-603`) reads the same route but returns only `finished_at`, `price_through` and `broker_through`, and `ByPublication` (`catalog.ts:58-81`) keeps nothing and rebuilds on every call while `/state` cannot answer. The screener must keep its current snapshot in that case, so neither is reused as is; the rule they implement (one build at a time, rebuild only on a new `finished_at`, checked at most every 60 s) is the same.
2. For each indexed file whose `sha256` is in neither cache, call `POST /xsection` for those names only, then download with `TerminalClient.file` (`terminal.ts:479`, public), which verifies sha256 and size and fills the memory and disk caches. A cached file is read without a grant (INFERENCE from `fetchFile`, `terminal.ts:487-500`, which looks in memory and on disk before it downloads). FACT: `TerminalClient.api` is private (`terminal.ts:414`), and changing `terminal.ts` would change the Backtest's `engine_version`; so `/state` and `/xsection` are called by a thin client in the screener-worker's own `refresh.ts`.
3. Decode each ticker through `priceSeries`.
4. Cross-check each ticker against its `/manifest`, read by the same thin client (no quota, no audit; 845 `/manifest` calls take 2.3 s from `sfo`, `BACKTEST_END_TO_END.md` §6.5 and §15): the ticker's last bar equals the newest `last` of its yearly price files (the rule `TerminalClient.manifest` uses for `last_bar`, `terminal.ts:575-590`), and its row count equals the sum of their `rows`. FACT: since [D-L3] was replaced, the Backtest catalog takes its flow date from `/state` and reads every stock's manifest only when `/state` is unavailable (`CONTRACT.md:77-83`); the screener's per-ticker check is its own integrity step, not a catalog build.
5. Compute the next snapshot (6.7) on the builder thread; swap all-or-nothing. Any integrity failure keeps the previous version, logs `REFRESH_FAILED` and retries with backoff. When the new index names exactly the files the replica already holds (the same sha256 set), the replica keeps its snapshot and only advances `published_at`: no download, recompute or swap (a publisher run writes a new `finished_at` even without a new session; MULTI-USER SCALE AND COST 6d.2). After a swap the previous snapshot is kept for `SCREENER_PREVIOUS_GRACE_S`, so requests pinned to it are still served (API CONTRACT §8.5; 6d.4).

**Correction to the design (FACT).** The draft design's step "cross-check every listed pack sha256 against `/manifest`" cannot run as written: `/manifest` returns yearly files with `bytes, rows, first, last, sha256` but no pack entries (`apps/terminal-api/app/main.py:307-314`; `m.get('packs')` is read only by `/bundle`, `main.py:372`). Step 4 above checks last date and row count instead. If a sha-level check is wanted, terminal-api `/manifest` can gain an additive `packs` field (readers ignore unknown fields: `terminal.ts:575-590` reads only `ticker`, `datasets`, price `years`). This is listed as an option in CHANGES AWAITING APPROVAL, not a requirement.

**M250.** INFERENCE: the new family is immune to M250 by construction. It is the first application of the user's chosen fix A (content-addressed keys; ERRORS M250, Solution and Status: "User 2026-10-27 13:27 UTC memilih A") and does not wait for the general publisher PR.

**Versions and freshness.**
- `price_data_version` = `datafile.dataVersion` over (ticker, `price`, pack sha256) for every ticker (`datafile.ts:271`). It uses the same inputs as the Backtest's data version for price (`apps/backtest-worker/src/load.ts:22-23, 163`).
- Every response carries `price_through`, `broker_through`, `broker_behind_sessions` and `published_at` (= `finished_at`) from `state.json` (`publisher.py:549-554`).
- Feature 04 `calculated_at` is not used: Feature 04 is not on the path.

**As-of policy.**
- Evaluation date E = `price_through`.
- Each ticker is evaluated at its own last bar on or before E. FACT: the Backtest does the same, with no filling (`CONTRACT.md` §2).
- **STALE** = last bar before E. FACT: 16 stocks on 2026-10-27, from ADHI (2026-08-21) to MSIN and TGKA (2026-10-26) (`audit/feature04.md` §8). Hidden by default through the visible chip "Traded on `E`"; when the user shows them, each row carries the remark `STALE` with its last bar date (DECIDED, P4, 2026-10-28).
- `bars_ago` counts the ticker's own bars. `market_sessions_ago` is informational. FACT: the 2026-09-17 and 2026-09-18 sessions are missing for every stock (ERRORS M238; `audit/verify_feature04.json` F04-06), so the two differ across that span.

**History.** Always the full published history. FACT: cumulative series never converge (NVI up to about 96,800%); EMA 200 is up to 7.7% off with a 500-bar tail; KAMA on BABP is still off by 1.3e-3 absolute (27.27348 vs 27.27221) with a 1,000-bar tail (`audit/verify_matrix_a.json`, `audit/verify_matrix_b.json`).

**Freshness consequence (FACT).** Between the price cron (10:00 UTC, `.railway/railway.ts:88-93`) and the end of the 19:00 WIB publication (about 13:03 UTC on 2026-10-27, ERRORS M250), the database holds a session the rack does not: about 3 h on each trading day. The Screener shows exactly what the Terminal and the Backtest show. Fresher data for everyone is a rack schedule decision (P1); a screener-only early build is not offered.

**Options rejected.**
- Per-ticker refresh as the primary path: 845-1,690 grants and audit rows per publication on one subscriber lock, a cold load of 50 s to 2.5 min, and a dependency on the TEMPORARY 1e9 quota override (`audit/benchmark.md` §4). Kept only as a TEMPORARY fallback adapter if P1(b) is chosen.
- A separate 10:20 UTC screen cron: a second data version across EDGE pages and an override of the user's schedule.
- A direct DB login in the worker: a credential in a compute service against the `CONTRACT.md` §1 pattern, a full read per version and per restart on a 128 MB `shared_buffers` database, and the same second time base.

**Quota (FACT/INFERENCE).** 2-4 files per publication fit the default quotas (`files_per_hour` 60, `megabytes_per_day` 300; migration `20261025_100:79-83`); the `REF` pseudo-ticker never counts as an opened ticker (`quota.py:5, 34`). The worker shares the gateway subscriber with the browser and the backtest worker (`audit/reuse.md` §3.2), so the quota is shared; INFERENCE: the screener adds about 15-30 MB per publication, and a restart with a warm disk cache adds nothing, because only files missing from the cache are granted (refresh rule 2). The design does not depend on the TEMPORARY override.

| Card | |
|---|---|
| Need | Whole-universe bars for every screen, from the data the Terminal and Backtest show, without per-request database reads or per-ticker grants |
| Class | Every whole-universe reader of the rack, including future macro and cross-asset files, needs one file family and one state route |
| Fix and layer | Data layer (publisher writes content-addressed files and the index), service contract (terminal-api routes), consumer (worker refresh with integrity checks) |
| Covers | Price, universe attributes, corporate actions, dividends (Phase 1); flow files (Phase 2, 6.11) |
| Does not cover | Historical as-of dates (6.13); a fresher-than-rack session (P1) |
| Risk and cost | A publisher run gains about 14 MB of upload (INFERENCE, from 14.22 MB of pack gzip) and a 2 s scan; two CLI deploys under the M248 procedure (CHANGES AWAITING APPROVAL A1-A2); one additive field on a route the backtest worker reads, with its existing `/state` tests kept |
| Verification | Cross-check on every load; fixture with one corrupted sha256: the swap aborts and the old version keeps serving; the version is unchanged across a reload of identical data and changes when a fixture changes one bar; publisher test: each slice equals its pack |
| Permanence | Permanent. The per-ticker fallback adapter is TEMPORARY |

### 6.6 Feature 04 role

**Decision (DECIDED, P2 a, user 2026-10-28): the brief's Option C (mixed model) without a runtime Feature 04 read.** Feature 04 keeps its broadly reusable features, unchanged; the Screener's defaults live in a smaller Screener snapshot, held in memory per publication rather than in a table; custom parameters are computed dynamically. The one restriction against the brief's wording: Feature 04 is not read at runtime, for the reasons below. DATABASE / FEATURE CHANGES §7.3 evaluates Options A, B and C as the brief defines them and answers the brief's Phase 5 questions. Feature 04 is unchanged (no column, VERSION, checkpoint, worker or migration change) and is not read at runtime. The default layer is the in-memory snapshot computed by `F` once per publication (6.7). Feature 04 keeps three roles: parity oracle in tests; optional per-publication reconciliation file (Phase 2, needs a SELECT grant on F04 to the new publisher group); AI consumer, unchanged (49 allowed columns, 57 calculation rows, `audit/feature04.md` §7).

Why it is not a runtime source (FACT unless marked): no precision gain (`F` equals the 15 stored columns, max relative difference 1.16e-15, `audit/benchmark.md` §2f); small coverage (9 of 53 fully, 2 partly, no OHLV, `audit/verify_feature04.json` F04-17 and additional findings); INFERENCE: it would save about 1.5 s of the 8.1-10.2 s of single-thread wall time per publication; two time bases (Feature 04 finishes at 10:09 UTC, the rack at about 13:03 UTC); repair coupling (the planned 2026-09-17/18 refill would put about 840 tickers into `REPAIR_REQUIRED`, `audit/verify_feature04.json` additional findings); no grant (live L1).

**Brief tension (recorded for the user, P2).** The brief expects "defaults from precomputed data" and says "Do not rebuild all historical indicators every day". This design persists nothing and recomputes the defaults in 8.1-10.2 s on one thread per publication (wall; first-repetition CPU 9.6-10.7 s, `evidence/benchmark/results/all53_full.metrics.json` and repeats). Exactness for recursive and cumulative indicators forbids tail windows (6.5 History), and incremental exactness needs checkpoint state per indicator, the same double implementation that rules out Option A (`audit/feature04.md` §11).

The evaluation of the brief's Options A, B and C, the Phase 5 answers, the oracle mapping and the parity verification are in DATABASE / FEATURE CHANGES §7.3.

### 6.7 Default (precomputed) and dynamic paths

**One path (PROPOSED).** A single function `series(id, params, output)`:
- **Key:** (`price_data_version`, `screener_engine_version`, `id`, `canonicalJson(resolveParams(BY_ID[id], params))`, `output`). `canonicalJson` is `apps/edge-bff/backtest/src/core/hash.ts:12`.
- **On a miss:** `Calc.out(key, params)` on full history; keep a tail of `SCREENER_WITHIN_MAX` + 1 bars per ticker plus `last_valid_index`: the longest `within` plus the previous bar a cross reads, 131 bars at the provisional 130 (API CONTRACT §8.9). The tail length is derived from that one variable, not written separately.
- **Precomputed and dynamic are one call made at two times**, so they cannot differ. Each cell reports `source: precomputed` (a pre-warm hit) or `dynamic`.

**Pre-warmed at each publication:**
- all 53 indicators at registry defaults, 76 outputs (I43 at anchor Week instead of its registry default Session, which P17 (a) does not offer; the consequence noted under P17, UNKNOWNS 13.2). Memory: 76 × 845 × 131 × 8 B ≈ 67 MB (arithmetic);
- every configuration the presets reference, read from `presets.json` at run time, never listed in code;
- contract-declared derived series, computed on the full series and then tailed: Donchian prior band, Bollinger-width rolling minimum, MA of an output;
- universe attributes: last close, previous close, 1D %, ADV20 = `signals.ts` `liquidity` (SMA20 of close × volume, the Backtest definition, `apps/edge-bff/backtest/src/core/signals.ts:174-176`), first and last bar, bar count, and the remark data of P4: stale flag with the last bar date, price-break flag with the action, its ex-date and ratios (6.12);
- default cross-sectional ranks (6.9);
- every preset's match and near counts on the default universe, stale and price-break tickers hidden (P4) (they replace the prototype's 26 browser screens at boot, `audit/html_ui.md` §3.13);
- each available preset's full result, put in the result cache below, since the counts computation evaluates it anyway, so a preset click is a cache hit (PAGE LOAD SEQUENCE 6c.4).

**On demand:** custom parameters, only for the tickers the planner keeps (6.10); partial per-ticker entries are allowed; an LRU bounded by `SCREENER_CACHE_BYTES`, dropped on a version swap. **Result cache:** keyed by data version, engine version, `screener_registry` and `definition_hash`, holding gzip response bytes; it holds no owner data, so users with the same screen share one computation (MULTI-USER SCALE AND COST 6d.2).

**Never precomputed, or never offered:**
- Raw level thresholds on OBV, PVT, A/D, NVI and PVI. FACT: their level depends on the start bar forever (`audit/verify_matrix_b.json` b-cumulative-start-dependence). They are offered only as change, ratio, N-bar high and level vs its own SMA with an explicit tie rule; EMA-based level states are computed on full history and labelled.
- Lengths above the caps (6.8).
- Past evaluation dates (6.13).

**Auditability.** A `snapshot_digest` (sha256 over every default tail) is logged per version.

**Phase 6 walk-through: RSI(14) default changed to RSI(7).** Each step of the brief, and where this design answers it differently:
1. *Not the precomputed configuration.* The key `canonicalJson(resolveParams(BY_ID.I13, {length: 7}))` differs from the pre-warmed default key, so the snapshot misses and the cell reports `source: "dynamic"`, `is_default: false`.
2. *Required lookback.* Always the full history from the ticker's first price row, not a computed lookback. FACT: tails are not exact for recursive rows (6.5 History). The output's `first_valid_bar` for length 7 (derived at build time, 6.8) decides `INSUFFICIENT_HISTORY`.
3. *Smallest eligible universe.* S0 universe filters, then the cheaper S2 snapshot conditions, then pruning (6.10); RSI(7) is computed only for the survivors.
4. *Load only the required data.* Nothing is loaded per request: the bars are already in the snapshot, so a screen reads 0 bytes from terminal-display (asserted in PERFORMANCE BENCHMARK PLAN 11b.3).
5. *Calculate RSI(7).* `Calc.out('rsi', {length: 7, source: 'close'})` on each survivor's full series; no other indicator is computed.
6. *Evaluate the condition.* `evaluate.ts` tests the cell at the ticker's evaluation bar.
7. *Return the value and match result.* The cell carries the value, pass or fail, and `eval_date` (API CONTRACT §8.5).
8. *Cache.* The `SCREENER_WITHIN_MAX` + 1 bar tail goes into the series LRU, keyed by data and engine version; the response goes into the result cache, keyed by `definition_hash`. No Backtest simulation runs.

| Card | |
|---|---|
| Need | Defaults served from precomputed values where that is cheaper and identical; custom parameters computed only for what the screen needs |
| Class | Any derived-value cache that can drift from its formula. One function at two times removes the drift by construction |
| Fix and layer | Pure core (`metrics.ts`) + worker snapshot lifecycle |
| Covers | All 53 indicators, default and custom; derived series; universe attributes; preset counts |
| Does not cover | Historical evaluation dates |
| Risk and cost | 8.1-10.2 s on one thread (wall; first-repetition CPU 9.6-10.7 s) and about 67 MB per publication (above); custom lengths bounded by caps |
| Verification | For all 53, explicit default parameters equal the snapshot bit for bit and give the same key; RSI(7) dynamic equals a direct `F.rsi`; the configurations Feature 04 stores but the snapshot does not pre-warm (`sma_50`, `ema_12`, `ema_26`, `ema_50`, `ema_200`) reach Feature 04's values through the dynamic path (TEST PLAN 10b.2); evaluating on the tail equals evaluating on the full series at every tail bar (`compare` reads only `i` and `i−1`, `conditions.ts:52-61`) |
| Permanence | Permanent |

### 6.8 One approved indicator contract (Phase 4 of the brief)

**Approved formula contract (FACT).** User decision 2026-10-25 (`EXEC.md:7876-7878`): "Yang ada kita sesuaikan saja dengan feature 4, tapi jika tidak ada kita pakai HTML." Indicators Feature 04 stores follow Feature 04 (TA-Lib seeds for ATR and ADX; RSI 0 on a flat window); the others follow the Terminal reference engine. `indicators.ts` `F` implements it and is verified against Feature 04, TA-Lib and that engine (`apps/edge-bff/terminal/tests/calc/PARITY.md`; INDICATOR MATRIX §3). The Screener adopts the contract unchanged through `F`; TradingView parity is not part of it and is unchecked (UNKNOWNS U12).

**Existing chain (FACT).** Workbook → `indRegistry.json` + `indicators.ts` `DEFAULTS`/`F` → `apps/backtest-worker/scripts/build-registry.mjs` → generated `backtest-registry.json` with `registry_version` = sha256(`indRegistry.json` + `indicators.ts`)[:16]. The worker exits on a mismatch (`apps/backtest-worker/src/server.ts:349`, main `010af1e`). `scripts/terminal_indicator_spec.py` generates the AI formula reference, including the Feature 04 mapping (its `feature04` column, line 29).

**Decision (PROPOSED).**
- **Do not edit `indRegistry.json` or `indicators.ts` now.** Any byte change bumps `registry_version`, and the CLI-deployed backtest worker then refuses to start (`registry_mismatch`, `server.ts:349`) until `backtest-registry.json` is rebuilt and the worker redeployed (`audit/verify_matrix_b.json` additional findings).
- **A generated `apps/edge-bff/screener/src/core/screener-registry.json`**, built by `apps/edge-bff/screener/scripts/build-screener-registry.mjs` (with `--check`) from three inputs:
  1. The base `backtest-registry.json`, unchanged. It stays the only contract for ids, keys, parameters, types, defaults, min, max, options, `not_accepted` and outputs.
  2. A hand-kept `screener-overlay.json` holding only product choices: `shape`, allowed tests per output, search synonyms (served through `/catalog`, so the page holds none) and display labels. It may also hold explicit overrides; each names its evidence, and a test checks it against the probe it overrides. One override is known: I09 `factor > 0`. FACT: factor 0 passes the degeneracy probe below (finite, varying output), yet gives 1,128 direction flips in 2,115 bars on BBRI against 60 at factor 3.
  3. Fields derived at build time by running `F` on deterministic series, for all 76 outputs:
     - `first_valid_bar` per output.
     - `history_class` (window, recursive, cumulative, calendar), by a cut probe: recomputed from bar 1000, a window-class output equals the full-history output once its window is full; recursive and cumulative outputs do not. Calendar class comes from an anchor parameter.
     - Display unit and `level_comparable`, by a scaling probe (OHLC × k, volume × m): an output that scales with k is a price level, comparable with close; one that does not move is dimensionless; one that scales with m is a volume quantity.
     - `price_compare_lag` per output and per side, by a lag probe: if `close > output` (or `close < output`) is never true at lag 0 while the output is finite, that comparison reads the output's previous bar. FACT: Donchian upper gives 0 same-bar hits against 29,041-54,652 with the prior bar on 844 tickers (`audit/verify_matrix_a.json`). The same probe runs on every transform, so `rolling_max(high, n)` and `rolling_min(low, n)` get lag 1 as rhs of a price comparison; Bollinger and Keltner upper stay at lag 0, because `close > upper` does occur.
     - `inputs` per (indicator, source), by a poison probe: each OHLCV field set to NaN in turn; the fields whose poisoning empties the output are its inputs. FACT: the base registry's `inputs` ignore the chosen source (I28, I29, I32 and I33 list [C] whatever the source; INDICATOR MATRIX footnote 23), so the base `inputs` are not shown. The same probe gives each option's volume need: on an instrument without volume (IHSG), a cell whose option needs volume (VWMA basis on I27) is NA `NULL_AT_EVALUATION` with that reason; no option is hidden for a named ticker.
     - Narrowing, in three derived rules. (a) Degeneracy probe at each numeric parameter's `min`: all-null, non-finite or constant output, or two band outputs equal on every bar, makes the minimum exclusive. FACT: `min: 0` on I09 factor, I11 multiplier, I12 start, increment and maximum, I19 constant, I23 weights, I43 band_1_multiplier, I49 and I53 volume_scale, I50 and I51 initial_value (`backtest-registry.json`); I19 constant 0 divides by zero, while an I23 weight of 0 is valid. (b) Floor probe: a parameter for which `F` gives the same output at x + 0.5 as at x is integer-only, whatever its registry type. FACT: `def()` floors every key matching `LENGTH_KEYS` (`indicators.ts:239, 249`); `annualization_periods` is typed `number`. (c) A parameter the base marks `not_accepted` with reason "not read by the calculation module" is hidden, and its stated value is never shown. FACT: `build-registry.mjs:37` writes the workbook default there without checking `F`, which is why I37 `include_current_bar` reads `false` while `F` includes the current bar (`scripts/terminal_indicator_spec.py:10, 136-138`; `audit/reuse.md` §7.2). The same rule hides I34 `timeframe` and I37 `reference_method`.
     - `cost_class` (O(N) or O(N·n)), from the work of `F` at two lengths on a fixture (the default `L1` and `L2 = max(1000, 50 × L1)`, at most a quarter of the bars), counted, never timed: V8 precise block coverage counts the executed source characters in a child process without the optimizing compiler (`--max-opt=1`); O(N·n) when the work grows at least five times, O(N) when at most twice, and a growth in between stops the build (`build-screener-registry.mjs` `costClass`, `costVerdict`). Changed 2026-10-29: the first build used the wall-clock ratio, which flipped classes under CPU contention.
     - The Feature 04 oracle mapping, read from `scripts/terminal_indicator_spec.py` (its `feature04` column, emitted as JSON by a new `--json` mode). The derived oracle rows (I25, I28, I29, I31, I32 and the Feature 01 rows of §7.3) are added to that column. The migration the script also generates (`20261025_102`, applied) does not read the column (`migration_sql` uses `source`, `talib`, `existing` and `notes`), and the script's `--check` proves its text unchanged.
     - **Caps**, by the rule "full-market cold compute at the cap ≤ `SCREENER_CAP_BUDGET_MS` on one thread", from `cost_class` and ns per bar. The ns per bar come from the Phase 17 run on the service, recorded in `BENCHMARK.md` with CPU and Node version, not from the 4-CPU sandbox (`audit/benchmark.md` §0); until then the caps are provisional (P5). A start-up micro-benchmark is rejected: caps that move with each restart would make a saved screen valid one day and refused the next. FACT inputs: CCI(1000) 7.93 s; O(N) kernels ≤ 0.09 s at n = 1000 (`audit/verify_matrix_a.json` a-cost-long-length).
- **Narrow-only rule:** the overlay and the derived narrowing may only narrow the base. Every transferable screener condition is therefore Backtest-valid.
- **TEMPORARY for the Backtest side.** The defects behind rules (a) to (c) and the Donchian lag belong to the registry and its build (`indRegistry.json`, `build-registry.mjs`, the Backtest's generic condition). Their fix waits for the registry release (P6; CHANGES AWAITING APPROVAL D2), which can adopt the same probes. Until then the live Backtest accepts I09 factor 0, shows the I37 label and offers the same-bar Donchian test (ERRORS M255-M258, recorded 2026-10-28; DATABASE / FEATURE CHANGES §7.5).

**Versions:** `registry_version` passed through; `screener_registry_version` = sha256(base + overlay + derived fields)[:16]; `screener_engine_version` = a content hash over screener core, the worker's `src`, the imported core and calc files, and the Node major version (the `version.ts` mechanism). `formula_version` per indicator = `registry_version`, which is global. A per-indicator hash is not offered: the 53 kernels share one file (`indicators.ts`), and splitting it would change the Backtest's `registry_version` (I3).

**Consumers.** The worker reads the generated file and refuses to start on a mismatch (and runs the backtest worker's own registry check through `build-registry.mjs`). The page reads only `/catalog`; the prototype's `XPARAM` is deleted. The Backtest is unchanged. Feature 04 Python is unchanged and linked by a test. AI catalogs are unchanged now.

**New indicators** (Ichimoku and any other not among the 53) go into `F` and `indRegistry.json` through a deliberate registry release with a backtest-worker rebuild (P6), never as screener transforms.

| Card | |
|---|---|
| Need | One metadata contract for the 53 indicators, with no hand-edited copy in the Screener, the Backtest, Feature 04 or the page |
| Class | Derived metadata copied by hand (the prototype's `XPARAM`; the I37 label) |
| Fix and layer | Catalog metadata as a generated artifact; values derived from the registry and from code at build time, not enumerated |
| Covers | Parameters, ranges, caps, shapes, tests, history class, inputs per source, comparison lags, oracle links |
| Does not cover | Folding the overlay into `indRegistry.json`, and fixing the base registry's defects for the Backtest (the registry release, P6) |
| Risk and cost | One generator script with its probes; an overlay entry per indicator; a `--json` mode in `scripts/terminal_indicator_spec.py` |
| Verification | `--check` re-derives every probe field and fails on a diff; start-up hash check; one overlay entry per base id and vice versa; narrow-only assertions; each override tested against its probe; the probe cases of TEST PLAN 10b.10 (cases where a rule applies and one where it must not); Python test that every oracle column exists in `features/feature04/engine.py` `COLUMNS`; pinned record `verification/screener/F04_PARITY.md` |
| Permanence | Permanent mechanism; the screener-only narrowing, `not_accepted` hiding and lag rules are TEMPORARY for the Backtest side, paired with the registry release (P6) |

### 6.9 Condition engine (Phase 8 of the brief)

**Metric references (wire grammar).**
- `{kind:'indicator', indicator, params, output}`
- `{kind:'price', field}`
- `{kind:'transform', fn, of, args}` with `fn` in `pct_distance`, `band_position`, `lag`, `change`, `rolling_max`, `rolling_min`, `rising_run`, `ma`, `ratio`, `vs_index`. These are condition arithmetic over `F` outputs and the exported `sma`/`ema`/`rma`, not formulas.
- `{kind:'pattern', type}` with `type` in `breakout`, `breakdown`, `volspike`, `macross`, `macd_divergence`, `squeeze`, `stoch_cross_in_zone`, `new_high`, `silent`, reusing `PRICE_ACTION`, `priceActionCondition` and `bullishDivergence` (`conditions.ts:124-190`) where they exist.
- `{kind:'flow', metric, params:{window, board}}` (Phase 2)
- `{kind:'xsection', metric:'return_rank'}`
- `{kind:'universe', attr}`

The lists above are today's content, not a list kept in code: the valid `indicator`, `fn`, `type`, `metric` and `attr` values are read from the generated catalog (`screener-registry.json` for indicators, `screener-metrics.json` for everything else, 6.12), and `validate.ts` and the page derive them from there.

**Tests.**

| Kind | Rule | Returns |
|---|---|---|
| VALUE | `gt`/`lt` strict; `between` inclusive and counted as one condition. `value > value2` is refused with `INVALID_CONDITION` (the prototype silently reorders, `audit/html_model.md` §4.1; a documented UX change; the UI validates first) | `value`, `unit`, `eval_date` |
| STATE | `compare(lhs, op, rhs)[at]`; lhs and rhs from price, an output, a value or a second instance (SMA50 vs SMA200) | `pass`, `lhs`, `rhs`, `eval_date` |
| EVENT | `crosses_above`/`crosses_below` through core `compare` (bar 0 never true, NaN false, both sides finite on the previous bar), or a pattern signal. `within` N from 1 to 130; j = the largest index in [at−N+1, at] where the signal is 1 | `event_date = dates[j]`, `bars_ago = at−j`, `market_sessions_ago`, current lhs and rhs, `last_event_date` within 130 bars |

An event is never reduced to a state. `combineEntry` is deliberately not used: FACT, its one window turns states into "true on any of the last W bars" (`conditions.ts:269-292`).

**NA reason codes** (per cell; they never fail the whole screen):

| Code | Meaning |
|---|---|
| `INSUFFICIENT_HISTORY` | The core's `INDICATOR_OUTPUT_EMPTY` (`conditions.ts:100`), caught per ticker with the `EXCLUDED_CODES` / `unlessLeftOut` pattern (`signals.ts:255`) |
| `NULL_AT_EVALUATION` | Zero band width, flat window, zero volume, an option that needs volume on an instrument without volume (IHSG) |
| `FLOW_UNAVAILABLE` / `FLOW_LAGGED` | Flow missing, or older than the policy allows (P10) |
| `NOT_APPLICABLE` | The metric's scope excludes the ticker (for example bank metrics outside Banks) |

A metric with no data at all is refused at validation with `METRIC_UNAVAILABLE`, so the UI shows it disabled. A stale ticker is not NA: it is evaluated at its own last bar (6.5) and carries the row remark below.

**Remarks (DECIDED, P4 and P4.1 A, 2026-10-28; codes PROPOSED).** A remark explains a value; it never changes PASS, FAIL or NA.

| Code | Level | Meaning |
|---|---|---|
| `STALE` | Row | The ticker's last bar is before E; carries `last_bar_date`. Hidden by default (chip "Traded on `E`") |
| `PRICE_BREAK` | Row | An unadjusted price-affecting action (rule in 6.12); carries the action type, `ex_date`, `ratio_old`, `ratio_new` and the observed close ratio. Hidden by default (chip "No unadjusted price break"). TEMPORARY until the D22 data-layer fix |
| `PRICE_BREAK_IN_LOOKBACK` | Cell | On a `PRICE_BREAK` row, a price-derived cell whose lookback contains the ex-date: its value and its pass or fail are shown, marked as distorted (P4.1 A) |

**Match and near miss.** `need = entryNeed(logic, at_least, active)` (`conditions.ts:263`; equal to the prototype's `needOf`). `met` counts PASS only. **One near rule for table, preview and CSV:** `near = !match && need ≥ 2 && met == need − 1`; this removes the prototype's second rule at line 1599 (`audit/html_ui.md` §3.15). `na_count` is returned.

**Sort.** Default: match, then met, then ADV20 descending, then ticker ascending (FACT: market cap does not exist, `audit/fundamentals_universe.md` §4). Per-cell sort key: the value for VALUE and STATE, `1000 − bars_ago` for EVENT. Nulls last in both directions.

**`rs_rank` (P7).** Population: active, non-stale stocks without a `PRICE_BREAK` remark and with a finite value at E, fixed before any condition (P4); a ticker the user shows through a chip is ranked against that population, so showing it moves no other rank. `pct = 100 · #(strictly lower) / (P − 1)`; NaN excluded (fixes the prototype's NaN-in-denominator defect, `audit/html_model.md` §7 item 9); ties share a rank; IHSG aligned with `asOf` (`datafile.ts:259`).

**Floating ties.** Raw doubles, no epsilon: identical to the Backtest. FACT: on flat windows, running-sum residue decides ties (BNBR, 358 of 358 disagreements, `audit/verify_matrix_b.json`). Mitigation: the liquidity and traded-on-E filters. A global tie rule would be a later core release.

**Reused unchanged (FACT, they exist):** `F`, `DEFAULTS`, `sma`, `ema`, `rma`, `isN`, `REGISTRY`, `BY_ID`, `resolveParams`, `Calc`, `compare`, `PRICE_ACTION`, `priceActionCondition`, `bullishDivergence`, `entryNeed`, `switchOns`, `liquidity`, `EXCLUDED_CODES`, `inflateVerified`, `priceSeries`, `brokerRows`, `corporateActions`, `asOf`, `dataVersion`, `flowData`, `brokerNet`, `rollingSum`, `top5Accumulation`, `TerminalClient`, and `catalog.ts` `regToCondition`, `legacyToCondition`, `DISPLAY` (`audit/reuse.md` §1).

**New pure code** in `apps/edge-bff/screener/src/core/`:

| File | Role |
|---|---|
| `contract.ts` | Wire types (imported by the page) |
| `validate.ts` | Refusals naming the field, the allowed values and the fix |
| `registry.ts` | Loads the generated registry |
| `metrics.ts` | Reference → series (6.7) |
| `transforms.ts` | Condition arithmetic |
| `evaluate.ts` | VALUE, STATE, EVENT at `at` |
| `match.ts` | Match, near, counts |
| `plan.ts` | Planner (6.10) |
| `xsection.ts` | Cross-sectional ranks |
| `flowmetrics.ts` | Flow metrics, including `topNAccumulation` (Phase 2) |
| `universe.ts` | Universe filters, shared with the page |
| `presets.json` | Presets |
| `screener-metrics.json` | Non-indicator metric catalog: definitions, `requires`, `applies_to`, `periods` (6.12) |
| `to-backtest.ts` | Backtest translation (6.15) |

**Legacy prototype metrics map onto the registry (P6).**

| Prototype | Mapping |
|---|---|
| `price_ma` | I01/I02 + `pct_distance`; EMA uses `F`'s SMA seed |
| `ma_cross` | Cross-instance state or event |
| `rsi`, `stoch`, `macd`, `adx` (+DI/−DI from I07), `bb`, `atr` (I31), `supertrend` (I09 direction) | Registry indicators |
| `breakout` / breakdown | Core `breakout` / a new pattern on the Donchian lower band at the lag the probe derives (6.8) |
| `volspike` | Core `volspike` (mean of the previous N) |
| `hi52`, `lo52` | VALUE on `pct_distance(close, rolling_max(high, N))` / `rolling_min(low, N)`, the window including today as in the prototype (a value, so no lag); N is the "one year" entry of the metric catalog's `periods` block: 252 (P23 a, decided with the go; the prototype used 250) |
| `ret` | I17 |
| `rs` | `vs_index` |
| `squeeze` | Bandwidth ≤ its `rolling_min` |
| `silent` | Transform pattern |
| `ichimoku` | Requires a registry release (P6) |

#### 6.9.1 Operator mapping

One row per prototype shape or key and operator (FACT for the prototype rules: `audit/html_model.md` §2.1, §2.2, §2.4, prototype lines as cited there; the pairs are those of `evidence/html_ui/catalog.json`). Wire forms are PROPOSED. A compound operator becomes one condition (a pattern or a transform), never two, so ANY and AT LEAST N count it once. "Kept" means the same meaning on `F`; "changed" gives the reason.

| Shape or key | Operators | Prototype rule | Wire form | Kept or changed |
|---|---|---|---|---|
| line (sma, ema, wma, hma, kama, vwma) | gt, lt, between | (c / line − 1) × 100 | VALUE `pct_distance(close, output)` | Kept |
| line | above, below | close vs line | STATE close gt / lt output | Kept |
| line | rising | line > line 5 bars ago | STATE output gt `lag(output, 5)` | Kept |
| line | xa, xb | close crosses the line | EVENT close crosses_above / crosses_below output | Kept |
| band (donchian, keltner, bollinger) | gt, lt, between | position (c − lower) / (upper − lower) × 100; NaN when width ≤ 1e-9 · c | VALUE `band_position(output)` | Changed: NA `NULL_AT_EVALUATION` only at zero width (raw doubles, R14) |
| band | abu, bll, abb | c > upper, c < lower, c > basis; Donchian on the prior-session band | STATE close gt upper / lt lower / gt basis, at the lag the probe derives (Donchian: 1) | Kept |
| band | xau, xbl | close crosses above upper, below lower | EVENT close crosses_above upper / crosses_below lower, same lag rule | Kept |
| band (vwap) | dist value, abb, xau, xbl | (c / vwap − 1) × 100; c > vwap; crosses of upper1 / lower1 | VALUE `pct_distance(close, vwap)`; STATE; EVENT | Kept; Week, Month, Quarter and Year anchors only (P17 a, decided; the Session anchor is not offered) |
| dir (supertrend, psar) | gt, lt, between | (c / line − 1) × 100 | VALUE `pct_distance(close, line output)` | Kept |
| dir | up; flipup, flipdn | dir = 1; flips | STATE direction gt 0; EVENT direction crosses_above / crosses_below 0 | Kept |
| osc (25 indicators) | gt, lt, between, xa, xb | the output; level crosses | VALUE output; EVENT output crosses value | Kept |
| pair (macd, aroon, stoch_rsi, stochastic, tsi, ppo, pvo, kvo) | level ops on line a | line a vs a value | VALUE / EVENT on the first output | Kept; KVO is `F`'s classic Klinger (P16 a, decided) |
| pair | asig; xsig, xsigd | a > b; a crosses b | STATE a gt b; EVENT a crosses_above / crosses_below b (same instance) | Kept |
| adx | level ops; plus; dixa | ADX; +DI > −DI; +DI crosses above −DI | VALUE / EVENT on `adx`; STATE `plus_di` gt `minus_di`; EVENT crosses_above | Kept |
| vol (volume_sma, volume_ema) | gt, lt, between; vabove; vxa | average volume; v > average; v crosses above | VALUE output; STATE volume gt output; EVENT volume crosses_above output | Kept |
| cum (obv, pvt, adl; nvi, pvi) | gt, lt | raw cumulative level | — | Disabled with a reason: the level depends on where history starts (6.7) |
| cum | cabove; cxa | line > EMA(line, 20; 255 for nvi, pvi); crosses above it | STATE output gt `ma(output, EMA, n)`; EVENT crosses_above | Kept on full history; label changed from "average" to "EMA", as the prototype computes |
| cum | crise | line > line 20 bars ago | STATE output gt `lag(output, 20)` | Kept |
| `price_ma` | above, below; xa, xb | close vs MA; close crosses MA | STATE / EVENT on I01 or I02 | Changed for EMA: seeded as `F` (SMA seed), P6 |
| `price_ma` | rising | MA[t] > MA[t − 21] | STATE output gt `lag(output, 21)` | Kept (21, not the line shape's 5) |
| `price_ma` | gt, lt, between | (c / MA − 1) × 100 | VALUE `pct_distance(close, output)` | Kept |
| `ma_cross` | golden, death; above | fast crosses slow; fast > slow | EVENT crosses_above / crosses_below between two I01 or I02 instances; STATE gt | Kept |
| `rsi` | gt, lt, between, xa, xb | legacy RSI | VALUE / EVENT on I13 | Changed: `F`'s convention on long flat stretches (DADA, 45 bars) |
| `stoch` | level ops; kxd | %K; %K crosses above %D | VALUE / EVENT on I15 `k`; EVENT `k` crosses_above `d` | Kept |
| `stoch` | kxd_os | K crosses above D on a bar where K < 25 (the label says 20) | pattern `stoch_cross_in_zone {zone_max}`, default 25 as coded | Kept as coded (K < 25); the label "below 20" is corrected to the coded test (P22 item 8, decided as recommended) |
| `macd` | xsig; zero | MACD crosses above signal; crosses above 0 | EVENT `macd` crosses_above `signal`; EVENT `macd` crosses_above value 0 | Kept |
| `macd` | bdiv | swing-low divergence, flagged 3 bars after the low | pattern `macd_divergence` (core `bullishDivergence`, same algorithm) | Kept |
| `macd` | hup | h[t] > h[t − 1] > h[t − 2] > h[t − 3] | STATE `rising_run(histogram)` gt value 2 (transform `rising_run`: consecutive bars with x[t] > x[t − 1]) | Kept |
| `macd` | gt, lt | the histogram | VALUE on I06 `histogram` | Kept |
| `adx` | gt, lt, between, xa; plus; dixa | as the adx shape | as the adx shape | Kept |
| `bb` | gt, lt, between | %B as a fraction | VALUE on I28 `percent_b` (a fraction in `F` too) | Kept |
| `bb` | below; brk | c < lower; close crosses above upper | STATE close lt lower; EVENT close crosses_above upper (I27) | Kept |
| `bb` | squeeze | bandwidth ≤ its minimum over `sq` bars, today included | pattern `squeeze {length, std_dev, lookback}` | Kept |
| `atr` | gt, lt, between | ATR / c × 100 | VALUE on I31 `natr` | Changed: `F`'s ATR seed (equal after warm-up) |
| `supertrend` | flip; bull | flipped to uptrend; in uptrend | EVENT direction crosses_above 0; STATE direction gt 0 | Kept |
| `ichimoku` | above, tk | cloud and Tenkan/Kijun rules | — | Disabled until a registry release (P6) |
| `breakout` | up; dn | c > max(h of the prior N bars); c < min(l of the prior N bars) | pattern `breakout` (core); pattern `breakdown` | Kept |
| `hi52`, `lo52` | gt, lt, between | (c / max(h over N, today included) − 1) × 100; same with min(l) | VALUE `pct_distance(close, rolling_max(high, N))`, `rolling_min(low, N)` | Changed: N = 252 sessions (P23 a, decided), the prototype's 250 |
| `ret` | gt, lt, between | (c / c[t − d] − 1) × 100 | VALUE on I17 `roc` | Kept |
| `rs` | gt, lt, between | stock return minus IHSG return over d | VALUE `vs_index(close, d)` | Kept |
| `rs_rank` | gt, lt, between | rank over all listings, NaN in the denominator | VALUE xsection `return_rank {window}` | Changed: fixed population, NaN excluded (P7) |
| `volspike` | gt | v / SMA(v, len) of the previous bar | pattern `volspike` (core) | Kept |
| `volspike` | lt, between, xa | the same ratio | VALUE / EVENT on `ratio(volume, lag(ma(volume, SMA, len), 1))` | Kept |
| `bandar` | acc, bigacc, dist, bigdist, gt, lt | ratio vs global thresholds 6 / 10 | STATE on the bandar ratio with per-condition thresholds | Disabled until P9 (Phase 3); global thresholds become per-condition (P22 item 5) |
| `bavg` | gt, lt, between | net-weighted typical-price proxy | VALUE `close vs top-3 buyer VWAP` | Disabled until P9 |
| `topacc` | gt, lt, between | top-N net over D | VALUE B1 `topN` | Kept (lossless to the Backtest at N = 5) |
| `broker` | gt, lt, between, xa | one broker's net over D | VALUE / EVENT B4 | Kept; default broker is P20 |
| `fnet`, `fpct`, `fstreak` | gt, lt, between (+ xa, xb for `fnet`) | foreign net, % of value, streak | VALUE / EVENT F1, F2, F4 | Kept; all boards by default (P8, decided), Regular as a labelled variant |
| `freq` | gt, lt, xa | trades / SMA(trades) of the previous bar | VALUE / EVENT D1 | Kept |
| `silent` | on | volume ratio ≥ volx while the move ≤ move % | pattern `silent {days, length, volx, move}` | Kept |
| `mfi`, `cmf` | level ops | legacy MFI, CMF | VALUE / EVENT on I47, I45 | Kept |
| `obv` | rising | OBV > SMA(OBV, len) | STATE output gt `ma(output, SMA, len)` | Kept |
| `obv` | high | OBV > max of the prior len bars, on every such bar | pattern `new_high {of, length}` (true on each bar above the prior `length`-bar maximum) | Kept |
| `adv` | gt, lt, between | SMA(c × v, len) / 1e9 | VALUE on price `liquidity()` | Kept (never broker-lagged) |

| Card | |
|---|---|
| Need | VALUE, STATE and EVENT semantics with event dates, per-condition `within`, ALL/ANY/AT LEAST N and near misses, explained per cell |
| Class | Condition semantics shared with the Backtest; the Backtest's entry window semantics differ on purpose |
| Fix and layer | Pure core (`evaluate.ts`, `match.ts`) over unchanged core `compare` and patterns |
| Covers | Every (shape or key, operator) pair of the prototype's technical and flow catalogue, mapped in 6.9.1 or disabled with a reason (Ichimoku, raw cumulative levels, bandar items until P9); NA reasons |
| Does not cover | A numeric near-miss distance (the prototype has none); a global tie rule |
| Risk and cost | `between` is a documented UX change (refuse instead of reorder) |
| Verification | gt, lt and crosses equal the Backtest's `conditionSeries[at]` on 200 tickers; `between` at value = min and = max; within boundaries (N−1 bars ago passes, N fails); bar 0, NaN, missing previous bar; a state true for 10 bars with no cross in N fails the event; Donchian prior band ≡ `breakout`; every NA code, including RANS (74 bars) and IHSG volume |
| Permanence | Permanent |

### 6.10 Query planner (Phase 7 of the brief)

**Stages (PROPOSED).**

| Stage | Evaluates | Note |
|---|---|---|
| S0 | Universe hard filters: stocks, sector and industry in/out (unclassified per P15), price, ADV, the stale and price-break chips (on by default, P4), history length, explicit tickers, universe metric filters | Conjunctive, outside `met`, safe for every logic |
| S1 | Population-level cross-sectional values (`rs_rank`) on the fixed population | Never pruned |
| S2 | Snapshot lookups | O(1) per ticker |
| S3 | Dynamic conditions, ordered by predicted cost (overlay `cost_class` × length × survivors' bars, calibrated by an exponentially weighted mean of measured ms) | |
| S4 | Completion pass over every remaining cell of each survivor | Displayed rows are complete |

**Pruning rule.** θ = need − 1 when need ≥ 2, else need. For a ticker with m passes and r unevaluated conditions, **prune iff m + r < θ**.

**Proof.** The final `met` ≤ m + r < θ ≤ need, so the ticker is not a match. When θ = need − 1, `met` < need − 1, so it is not near either. FAIL and NA never add to `met`. Every function is pure and keyed by (ticker, reference), so evaluation order cannot change a value. Displayed rows are fully evaluated (S4).

| Logic | Effect |
|---|---|
| ALL | Prune at the second failure (at the first when need = 1) |
| AT LEAST k | Prune when failures exceed n − θ |
| ANY | No pruning; `meta.plan` says so |

**Counts and budget.** Each condition reports `evaluated`, `passed`, `na` and `exhaustive`. `options.exhaustive = true` disables pruning; FACT, an exhaustive 3-condition screen takes 0.35-0.56 s (`audit/benchmark.md` §2c). The worst case is costed before running; above `SCREENER_MAX_CPU_MS` the request is refused with `LIMIT_EXCEEDED {limit:'compute_budget', allowed, needed, costliest}`, never cut short. A cancel flag is checked between tickers.

**Per-condition counts under pruning.** A condition's `passed` is exact only when its `exhaustive` is true. S2 snapshot conditions are evaluated on every S0 survivor (O(1) per ticker), so their counts are always exact. An S3 condition pruned on some tickers is shown as "m of `evaluated` evaluated", with the tooltip "counted on the tickers that can still match or be near; run exhaustively for the full count", never as "m of U" (FRONTEND INTEGRATION 9.2). The API example shows the case: condition c, `evaluated` 171 of 340 eligible (API CONTRACT §8.5).

| Card | |
|---|---|
| Need | Avoid computing expensive custom conditions for tickers that can no longer match or be near, without ever removing a possible ALL/ANY/AT LEAST N result |
| Class | Any multi-condition evaluator over a universe |
| Fix and layer | Pure core (`plan.ts`) |
| Covers | Every logic, every condition kind |
| Does not cover | ANY (no safe pruning exists); it relies on the cost budget instead |
| Risk and cost | A planner bug could hide a match; the property test below guards it |
| Verification | Property test over random definitions (ALL, ANY, AT LEAST; 1-20 conditions mixing precomputed, dynamic and cross-sectional; many seeds): pruned output equals exhaustive output for the match set, near set, every displayed cell, `met` and `na_count`, and every condition marked exhaustive has the exhaustive run's `passed`; a second test: stage order does not change the result |
| Permanence | Permanent |

### 6.11 Flow and bandarmology (Phase 9 of the brief)

**Facts the design rests on** (`audit/flow.md` §1-5; `audit/verify_flow.json`):
- F06 stores Regular-board (and Nego, Tunai) foreign net for 1/5/10/20/40/60 sessions, % of value for 1/5/20, buy days, z-scores and percentiles (null until 252 + N sessions), strength and acceleration, on each ticker's own sessions. The latest cross-section reads in 23 ms.
- Broker-ranking metrics (top-N broker net over D sessions, bandar average price, D-session breadth) are stored nowhere.
- Multi-date F05 and F06 aggregates re-run at 3-8 s, with one timeout above 30 s (`audit/verify_flow.json` refuted C12).
- F02 on the latest date is sparse: ANTM 20-day foreign net −408.05 B (Regular −408.39 B plus Nego 0.34 B) against a true −477.11 B.
- F02 and F06 commit per ticker during a round of about 37 min (`apps/stockbit-updater/refresh.py:68-75, 117-140`).
- One round runs per stockbit-updater deployment; there is no schedule (refuted C2).
- No bandar definition is approved (`verification/terminal_api/DESIGN.md:40, 147`).
- Board choice changes the 20-day foreign net for 168 of 841 stocks; 20 flip sign.
- Price volume equals Regular-board volume (C9).
- Stockbit's "Foreign Flow" equals the Regular board (BMRI, 16 dates), and the user kept all boards as the Terminal's default display (ERRORS M244, 2026-10-27); on 2026-10-28 the user chose all boards as the Screener's flow default too (P8, DECIDED).
- F06 holds a row per board only on the dates that board traded, and its windows run on the ticker's sessions with every board zero-filled (APPENDIX B §B.3); its catalog warns "Do not compare across boards or sum across boards".

**Decision (PROPOSED), Phase 2: two xsection files in the same publication.**
- `flow_f06`: the latest complete date's stored F06 columns per board (the Regular variant and the self-check oracle), plus one-day series per ticker and board of the additive components `foreign_buy_1d`, `foreign_sell_1d`, `domestic_buy_1d`, `domestic_sell_1d` and the four `*_freq_1d` columns; net, traded value `foreign_buy_1d + domestic_buy_1d` and trade count `foreign_buy_freq_1d + domestic_buy_freq_1d` derive from them (FACT: buy and sell frequencies are equal on 865 of 865 latest rows, C8). Series length: 130 sessions for the windows of this section; the all-board z-score and percentile metrics (F5) need 252 + N sessions (312 for N = 60; FACT: 830 of 844 universe stocks have at least 312 F06 Regular sessions, APPENDIX B §B.2), so the final length follows the indicator set chosen from FLOW INDICATOR PROPOSALS (PHASE 2), and the file size is measured at the first run (U4). That section (16.10) proposes building the long all-board series from Feature 03 instead, with a SELECT grant on it, because a 312-session F06 series costs far more per publication; the source is chosen with the indicator set (its decision D9).
- `broker_window`: raw F05 rows `d,b,i,m,bv,sv,bl,sl` for the last 41 complete sessions, in the existing broker encoding, decoded by `datafile.brokerRows` (`datafile.ts:183`). Size INFERENCE: about 1.0 M rows (24,860 rows on 2026-10-27) and 8-12 MB gzip. 41 = D ≤ 20 plus `within` ≤ 20 plus 1.
- **Read per date with literal bounds.** FACT: a calendar-CTE join planned a seq scan of F06 taking 18.6 s (`audit/flow.md` §5 Q2).
- **Completeness from the data.** A date d is included only if the F06 Regular row count at d equals the number of tickers with F05 Regular rows at d. This excludes a mid-round partial F06 and avoids the stale RUNNING-row trap in `Monitoring_Stockbit_Update` (`audit/verify_flow.json` additional findings). No grant on the monitoring table is needed. FACT (live L5): the two counts are equal on completed dates, 865 = 865 on 2026-10-27, 862 = 862 on 2026-10-23, 859 = 859 on 2026-10-01; a date with 0 = 0 (2026-10-24, a Saturday) is not a session and is skipped.

**In the worker.**
- **All boards, the default (P8, DECIDED):** the one-day components of the board rows present on each date are summed per date on the ticker's sessions, and every window and every non-additive metric (% of value, shares, buy and sell days, z-scores and percentiles, flow vs previous window, strength, frequency ratios) is recomputed from those sums with the F06 definitions; stored per-board fields are never added across boards.
- **Regular variant:** stored windows are read directly.
- Custom foreign-net and %-of-value windows, the signed streak and the trade spike `trades_t / mean(prior n)` are computed from the series on ticker sessions (the F06 calendar).
- Broker metrics use `flow.ts` `flowData`, `brokerNet`, `rollingSum` and `top5Accumulation` on the ticker's price bars (the Backtest calendar). Two calendars therefore exist side by side; whether to keep both, each labelled on its cells, or to use one, is P20.
- `topNAccumulation` lives in screener core, with a test that N = 5 equals `top5Accumulation` bitwise (`flow.ts:108-119`). **TEMPORARY**: a second implementation of a shared Backtest formula, placed outside `flow.ts` only because every core file enters `engine_version` (`apps/backtest-worker/src/version.ts:18-21`). The general fix is a planned core release that generalises `flow.ts` to top-N with `top5Accumulation` = top-N at N = 5, in one deliberate `engine_version` change, like the registry release (P6). Until then a test pins `flow.ts`'s content hash, so any change there forces a review of the copy. The same rule applies to any later screener copy of a core function.
- **Self-check on every load, per board:** each board's recomputed 5/10/20/40/60-day sums and 1/5/20-day ratios must equal that board's stored F06 rows wherever the ticker has the sessions, so the summed all-board values rest on checked components. FACT (Regular): they match on 847 and 833 of 865 rows; every difference is a short history (C5). A mismatch marks flow `DATA_INTEGRITY` and makes flow cells NA.

**Proposed flow metric set (own flow screener, built on governed columns; `audit/flow.md` §4).** This is the audit's starting set; the Phase 2 set is chosen from FLOW INDICATOR PROPOSALS (PHASE 2). "F06 stored" in the Source column means stored for the Regular variant; at the all-board default the same definition is recomputed from the summed one-day series.

| ID | Metric | Source | Phase |
|---|---|---|---|
| F1 | Foreign net over N sessions (Rp B) | F06 stored N ∈ {1,5,10,20,40,60}; other N from the series | 2 |
| F2 | Foreign net % of traded value | F06 stored N ∈ {1,5,20}; others from the series | 2 |
| F3 | Foreign net-buy day ratio | F06 `foreign_buy_days_{5,10,20,40}d` | 2 |
| F4 | Foreign streak (signed) | Series | 2 |
| F5 | Unusual foreign flow (z-score, own-history percentile); null when history is short, disclosed | F06 stored | 2 |
| F6 | Foreign flow acceleration | F06 `foreign_flow_vs_prev_20d/40d` | 2 |
| F7 | Foreign strength | F06 `foreign_strength_20d/50d` | 2 |
| F8 | Cross-sectional percentile of F2 | Computed over the fixed population (P7) | 2 |
| B1 | Top-N broker net over D sessions | `broker_window` + `topNAccumulation` | 2 |
| B4 | Single-broker net over D sessions (any of the 112 `IDX_Broker_Profile` codes, D ≤ 20) | `broker_window` + `brokerNet` | 2 |
| D1 | Trade-count spike | Series | 2 |
| D4 | Foreign participation | F06 `foreign_buy_share_1d`, `foreign_sell_share_1d` | 2 |
| B2/B3/B5 | Bandar ratio, close vs top-3 buyer VWAP, D-day breadth | After definitions are approved (P9); shipped disabled with a reason | 3 |
| C1 | Institutional vs retail net | Deferred: current-state broker classes, not point-in-time | — |

Thresholds are per-condition parameters, never the prototype's global `BANDAR` object. When approved (P9): `bavg` uses the gross VWAP Σbuy_value / (Σbuy_lots · 100) of the top-3 net buyers (FACT: equals Stockbit Avg Buy, C10); breadth = buyers / (buyers + sellers) (FACT: F03's ratio is not equivalent, `audit/verify_flow.json` row correction B5).

**Mapping of the prototype's flow metrics.**

| Prototype | Source / status |
|---|---|
| `fnet` | F1; D + `within` ≤ 130 |
| `fpct` | F2 |
| `fstreak` | F4 |
| `freq` | D1 |
| `broker` | B4 |
| `topacc` | B1 |
| `adv` | Price `liquidity()`, never broker-lagged |
| `mfi`, `cmf`, `obv` | Registry I47, I45, I40 |
| `silent` | Technical transform |
| `bandar`, `bavg` | Phase 3, after P9 |

**Board (DECIDED, P8 b, user 2026-10-28).** All boards by default, recomputed from summed one-day components as above; a Regular variant, labelled, for comparison with Stockbit (ERRORS M244). Every flow reference carries `board`. At the default, `fnet`, `broker` and `top5` transfer with the same formula to the Backtest, which uses all boards (`apps/edge-bff/backtest/src/core/flow.ts:8-14`); the Regular variant is listed as left out (6.15). FACT: the Backtest evaluates flow on the ticker's price bars and skips a broker row on a date without a price bar (`flow.ts:6-7`, `unmatched_rows`), so on Nego-only days the values differ (81 stock-days of 15 stocks in the 20 sessions to 2026-10-27, TRUK +130.5 B of foreign net; `evidence/flow_proposals/verify_v14_nego_only_days.txt`, FLOW INDICATOR PROPOSALS 16.10); the handoff names those stocks.

**Freshness.** `flow_through` is the last complete date; every flow cell carries its `eval_date`. `FLOW_LAGGED` applies when the lag exceeds the user maximum, default 1 session (P10). INFERENCE: the 19:00 WIB run can start before a round finishes (round 11:08-12:58 UTC vs run start 12:05 UTC on 2026-10-27), so flow then catches up at the next publication.

**Grants.** A forward migration creates `terminal_publisher_feature_reader` (NOLOGIN) with SELECT on `Feature_06_Foreign_Domestic` (optionally `Feature_04_Technical_Indicator` for the reconciliation file), granted to `terminal_publisher_login` only. FACT: `terminal_market_reader` also serves `terminal_api_login` (live L2), and `scripts/provision_terminal_logins.py:15-31` rolls back unless each login reaches exactly its listed relations, so a grant to the shared group would widen terminal-api too.

**Options rejected.** A SQL Feature_07 table (a second top-N formula and inline stockbit-updater coupling; revisit through onboarding if the AI needs these metrics); a DB read in the worker; per-request F05 or F06 aggregates; F02 latest rows (sparse).

| Card | |
|---|---|
| Need | Flow screens on real broker and foreign data without recomputing large broker aggregates per request |
| Class | Any per-request aggregate over a large, cache-starved table (here F05, 46 M rows on a 128 MB buffer pool); the same mechanism will serve macro or cross-asset series |
| Fix and layer | Data layer (publisher window files with a completeness gate) + pure core metrics; grant in a forward migration |
| Covers | F1-F8, B1, B4, D1, D4 on all boards by default and as a Regular variant; Backtest-compatible `fnet`, `broker`, `top5` |
| Does not cover | Bandar ratio, `bavg`, breadth (P9); institutional vs retail (not point-in-time) |
| Risk and cost | INFERENCE: about 10-40 s of DB time per publication in per-date index reads; the exact per-date statements get a bounded read-only `EXPLAIN (ANALYZE, BUFFERS)` before the Phase 2 go (NEXT ACTION 15.1), confirmed at the first run. Flow lag recurs without a token |
| Verification | Self-check per board; `topN(5)` ≡ `top5Accumulation`; all-board `fnet`/`broker` ≡ Backtest `flowCondition` on published broker files for sample tickers; summed-component fixture (a Nego row absent on the evaluation date: the all-board 20-day net comes from the one-day sums, never from adding stored rows); completeness-gate fixture (partial date excluded); lag fixture |
| Permanence | Permanent; the bandar items wait for approval |

### 6.12 Fundamentals and universe filters (Phase 10 of the brief)

**Ships in Phase 1 (FACT: the data exists).**

| Filter | Source and rule |
|---|---|
| Security type | `stock`. FACT: `IDX_Stock_Universe` also types the three DIRE real-estate funds XCID, XCIS and XSPI `stock/common`, with sector and industry `Undefined` (`audit/fundamentals_universe.md` §4): a data-layer classification defect, recorded as ERRORS D30 (2026-10-28) with its general fix (an instrument type or subtype in `IDX_Stock_Universe`), never a list of names in code (P15) |
| Sector and industry, include and exclude | The reference file `ref/tickers.json.gz`, written by the publisher from `IDX_Stock_Universe` (`publisher.py:418-431`), with the groupings and counts of the Backtest's `groupingsOf` (`catalog.ts:20-31`): 11 sectors and 58 industries (live L7). A stock without a classification (source value `Undefined`: XCID, XCIS, XSPI; IHSG is an index and not counted) is unclassified: counted apart, never a value (`terminal.ts:156` `classification`; ERRORS D02 lesson, A1.4). An include filter keeps unclassified stocks only through an explicit "include unclassified" option; an exclude filter leaves them in. Never `Universe_Equity_Description`, which has the two columns swapped (841 of 844 rows differ; the other 3 are `Undefined` in both; ERRORS D23) |
| Price ≥ | Last close; prototype default Rp 50 kept |
| 1D | Snapshot |
| ADV20 ≥ | `liquidity()`; median ratio 1.0001 to the exact Regular value (`audit/fundamentals_universe.md` §4.1); prototype default Rp 1 B kept (353 stocks with price ≥ 50 on 2026-10-27, before the stale filter) |
| Traded on E | Stale and suspension proxy, labelled as such. Chip "Traded on `E`", on by default: stale tickers are hidden, and the chip names how many (16 on 2026-10-27). Turned off, they are listed with the row remark `STALE` and their last bar date (DECIDED, P4) |
| Price break | Derived, **TEMPORARY** until the D22 data-layer fix (CHANGES AWAITING APPROVAL E2). Rule: a price-affecting action (`PRICE_ACTION_TYPES`) from the `actions` file with `ADJUSTED_HISTORY_BOUNDARY` (2026-09-12) ≤ ex-date ≤ the ticker's last bar. FACT (live L6): 8 tickers on 2026-10-27 (FORU, BAJA, ENRG, VKTR, BRNA, AHAP, PBSA, BUVA); the 5 actions dated later are not flagged until their ex-date is in the data. PBSA on 2026-10-27 in Feature 04: `rsi_14` 22.8, `sma_50` 706.4 against close 302 (ERRORS D22; `audit/verify_feature04.json` row correction F04-23). Effect (DECIDED, P4 and P4.1 A, user 2026-10-28; mechanism PROPOSED): the chip "No unadjusted price break", on by default, hides every flagged ticker and names how many. Turned off, the ticker is listed with the row remark `PRICE_BREAK` (action type, ex-date, `ratio_old`, `ratio_new` and the observed close ratio across its ex-date), in rows and preview. Its values are shown (P4.1 A); a price-derived cell whose lookback contains the ex-date carries the cell remark `PRICE_BREAK_IN_LOOKBACK` (6.9). The lookback comes from the output's `history_class` and window (6.8): a window-class output only while its window contains the ex-date; recursive, cumulative and calendar outputs always after the ex-date, because they read full history. Flow cells, ADV20 (close × volume barely moves across a split) and universe attributes carry no cell remark. The ticker stays outside the rank population (6.9). **Not covered:** an action missing from `idx_event_annotation`; an unadjusted action before the boundary (D22's "adjusted once at the bulk load" is suspected, not verified; RAJA's 2026-07-16 split is adjusted, live L6); and the Terminal, the Backtest, Feature 04 and AI answers, which stay distorted until the data-layer fix |
| History length ≥ N bars | Censored at 2018-01-02 |

**Phase 2, after validation:** dividend yield TTM by ex-date and years with dividends, from the `actions` file (`idx_event_annotation`: 5,301 DIVIDEND events; 568 of the 844 universe stocks have at least one). Adjustment basis (ERRORS D10, Part A3.14): with D22's mixed price bases, a TTM window that contains a price-affecting action is NA `MIXED_ADJUSTMENT_BASIS`, or its amounts are rescaled with `ratio_old` / `ratio_new` (the rule is P11). Special dividends are included and disclosed. Validated against an independent sample first (U8).

**Shown disabled with a reason, never a silent no-op:** market cap (bucket, filter and column; EXEC-MCAP waits for "go"); index membership, listing board, special notation and FCA (**the prototype's default `exclNotation: true` becomes off**), free float; the 28 statement metrics, Piotroski, Altman, Magic rank; NIM, NPL, CAR, CASA and LDR with `applies_to: Industry = Banks` (48 banks) and `NOT_APPLICABLE` elsewhere.

**Presets.** A preset is enabled only when every one of its conditions is AVAILABLE; it never runs with a leg removed, which under ALL would silently change the screen. "Load without the unavailable legs" is offered only as an explicit user action that lists the dropped legs, and the result is the user's own screen, not the preset. Per preset (conditions as coded, APPENDIX A §A.2):

| Ships in | Presets |
|---|---|
| Phase 1 | Technical: `brk52`, `oversold`, `golden`, `macddiv`, `rebound`, `squeeze`, `stflip`; `minervini` (with `rs_rank`, P7) |
| Phase 2 | Bandarmology without a bandar leg: `fstreak` (all boards, P8), `freq`, `follow` (default broker P20; all boards, P8) |
| Phase 3 | Presets with a bandar leg, after P9: `bigacc`, `silent`, `bavg` |
| Registry release | `ichi` (Ichimoku, P6) |
| Disabled (P11) | Fundamental: `graham`, `piotroski`, `magic`, `quality`, `garp`, `deep`, `bank`; `dividend` (payout has no data; a labelled variant without payout is a P11 option). Combined: `canslim`, `qflow`, `vacc`, each with a reason naming its unavailable legs |

**Availability is derived at run time**: `AVAILABLE`, `REQUIRES_DATA`, `REQUIRES_DECISION` or `NOT_APPLICABLE`. Indicators take it from the generated registry. Every other metric takes it from a new data file, `apps/edge-bff/screener/src/core/screener-metrics.json`, checked by the generator like the registry. Each entry carries id, group, parameters with ranges (flow maxima derived from the published window), `requires {file, columns}`, an `applies_to` predicate (for example `Industry = Banks`), unit, formula, plain-language interpretation, misuse warning and evidence path. These are the `Feature_Catalog` fields, so a later AI onboarding can reuse them. It covers the 32 fundamental metrics, F1-F8, B1, B4, D1, D4, transforms, patterns and universe attributes, plus a `periods` block (the session counts of 1M, 3M, 6M and 1Y: 21, 63, 126 and 252, P23 a, decided). A metric is AVAILABLE when the files and columns it `requires` are in the `state.json` index. Nothing is enumerated in UI or validation code, and a future macro or cross-asset file family becomes available by adding entries only.

**Point-in-time requirements for future data:** availability or filing date, vintages, period type, currency, split basis aligned with price (`ERRORS_AND_SOLUTIONS.md` A2.7). Fundamental values are "today only" and never used historically.

**Disclosed:** five tickers have F06 rows but are outside the universe and the price table (AKKU, CRAB, GTBO, TRUE, UNSP; `audit/verify_flow.json` additional findings; with ETFs, 37 F06 Regular tickers are outside, `audit/flow.md` §1). The publisher and the worker count flow rows whose ticker is not in the reference file and log the count (`orphans` in the refresh log line); no ticker is named in code. Root cause SUSPECTED, recorded as ERRORS D29 (2026-10-28) with its check; include or exclude is P20.

| Card | |
|---|---|
| Need | Universe filters on real data; no fabricated fundamentals; bank metrics separated |
| Class | A UI capability whose data does not exist; the same mechanism (derived availability from `screener-metrics.json`) covers future macro or fundamental sources |
| Fix and layer | Data (the existing reference file, the `actions` file) + catalog metadata (availability derived at run time) + validation (`METRIC_UNAVAILABLE`) |
| Covers | Sector, industry, price, ADV, traded, price breaks (hidden by default, shown with remarks), history length; dividends in Phase 2 |
| Does not cover | Market cap, index, board, notation, free float, statements (no data); the price-break distortion outside the Screener (D22) |
| Risk and cost | The shipped catalogue looks smaller than the prototype (RISKS / TRADE-OFFS R8) |
| Verification | Sector only from the reference file (swapped-UED fixture must not leak); ADV ≡ `liquidity()`; unclassified stocks counted apart and kept only by the explicit option; IHSG excluded; every disabled item carries a reason; removing `flow_f06` from the index turns every flow metric `REQUIRES_DATA` while technical metrics stay; the price-break cases of TEST PLAN 10b.4 |
| Permanence | Permanent mechanism; the disabled set shrinks as data arrives. The price-break rule is TEMPORARY, paired with E2 (D22) |

### 6.13 Screen Performance History (Phase 15 of the brief)

**Decision (PROPOSED, P14, open; Phase 1 ships the relabelled view): defer the Portfolio123-style feature.** The prototype's view is relabelled for what it is: "Stock vs IHSG", rebased, 1M/3M/6M/1Y. FACT: it has no rebalance, no holding rule and no historical universe (`audit/html_ui.md` §3.9). It is served by `/preview` from snapshot bars, with IHSG aligned by `asOf`.

**Why defer (FACT).** The price table holds 0 delisted tickers (survivorship); sector history starts on 2026-09-28 and there is no index, board or notation history; price history mixes adjusted and raw segments (RAJA adjusted across its 2026-07-16 split, PBSA raw across its 2026-10-14 split; D22, whose "adjusted once before 2026-09-12" is suspected, not verified), so past level filters look ahead; broker classes are current-state; there are no fundamentals (`audit/fundamentals_universe.md` §3.4).

**Rejected.** A labelled non-point-in-time technical evaluator now (survivorship makes every curve look better); the Backtest engine (12-ticker cap; the worker must not change).

**Path to un-defer.** A point-in-time universe including delisted tickers and a data-layer fix for adjusted prices (D22), then either `evaluate.ts` at past `at` (no new engine) or a Backtest screen-universe release. **TEMPORARY deferral.**

### 6.14 Saved screens, My metrics, watchlist (Phase 16 of the brief)

**Facts.** No server storage exists for these objects (`audit/edge_conventions.md` §3.1). The `edge_bff` per-owner tables are the precedent; the prototype uses `localStorage edge-*` keys. The EDGE shell keeps leftover CSS only: rules for a Watchlist page (`.watchlist-page`, `apps/edge-bff/static/index.html:2494, 9106`), for a multi-list selector with a "new watchlist" button (`.watchlist-selector`, `.new-watchlist`, `index.html:8219-8286`) and for a `.nav-watchlist` nav item (`index.html:6911`). No markup, script, table or API uses them (grep at `010af1e`; `audit/edge_conventions.md` §3).

**Decision (DECIDED, P12 a, user 2026-10-28, one watchlist; schema PROPOSED).** One forward migration in house style creating `edge_bff.screener_items` (kind `screen` or `metric`) and `edge_bff.watchlist_items` (schema in DATABASE / FEATURE CHANGES §7.2). Definitions are validated on write through the worker's `/v1/validate` and re-validated on load; a parameter that became invalid shows "needs review" with the field and is never adjusted. Limits `SCREEN_LIMIT` and `WATCHLIST_LIMIT` answer 422, following the `PIN_LIMIT` precedent (`apps/edge-bff/app/store.py:319-320` at `010af1e`). `localStorage scr.*` holds only conveniences: theme, panel sizes, the last open screen (the `edge-*` prefix is the EDGE shell's namespace on the same origin).

Not built: with P12 (a) decided, the TEMPORARY local adapter of P12 (b) is not needed.

| Card | |
|---|---|
| Need | Saved screens, My metrics and a watchlist that survive browsers and devices |
| Class | Per-owner UI objects; same mechanism as `conversation_ui` |
| Fix and layer | Data model (`edge_bff` tables with exact grants) + backend validation |
| Covers | Save, load, rename, duplicate, delete, watch and unwatch |
| Does not cover | Several named watchlists (P12 decided one). Every row is keyed by `owner_key`, so several users need no schema change; how EDGE serves several users is designed in MULTI-USER SCALE AND COST |
| Risk and cost | One migration plus provisioning and test changes |
| Verification | Migration refusal tests; owner filter on every statement; stale `revision` → 409; re-validation flags a definition whose parameter left the registry range |
| Permanence | Permanent |

### 6.15 Send to Backtest (Phase 14 of the brief)

**Decision (PROPOSED, P13).** One portable definition is used for run, save, CSV metadata and the handoff. `to-backtest.ts` is a pure translation with an explicit classification. It takes the Backtest catalog's `limits` as an input instead of numbers of its own: `max_portfolio_tickers` (12 today; `BACKTEST_MAX_PORTFOLIO_TICKERS` may only lower it), `window_bars {min, max}` (1-20) and `max_conditions` (`BACKTEST_MAX_CONDITIONS`). FACT: `apps/edge-bff/backtest/src/core/contract.ts:337-342` (`Limits`), `apps/backtest-worker/src/config.ts:21, 75-82`, `conditions.ts:259` (`WINDOW_BARS`); the Backtest page already slices with `CAT.limits.max_portfolio_tickers` (`app.ts:77`). The screener page reads them from `GET /api/v1/backtests/catalog` (same origin, session) before it builds a handoff, so a lowered limit on dev never produces a handoff the Backtest refuses.

| Lossless | Lossy (to `left_out`, with a reason) |
|---|---|
| Registry indicator conditions `gt`, `lt`, `crosses_above`, `crosses_below` with lhs price or output and rhs output or value of the same instance, parameters valid by the narrow-only rule, sent as `RegCard` | `between` |
| Supertrend or PSAR direction | Cross-instance comparisons other than core SMA `macross` |
| Core patterns: `breakout` up, `volspike`, SMA `macross`, `macd` divergence, crosses and histogram | Transforms and screener-only patterns |
| Donchian prior band ≡ `breakout` | Per-condition `within`, unless every event shares one N ≤ `window_bars.max` **and** there is no state or value condition (FACT: `window_bars` applies to states too, `conditions.ts:269-292`) |
| All-board `fnet`, `broker`, `top5`, the default board (P8) (Rp B → IDR via `DISPLAY`); same formula, with a note for a stock that traded on a Nego-only day in the window, which the Backtest's price-bar calendar skips (6.11) | The Regular variant of any flow metric; top-N with N ≠ 5; ratios, VWAP, streak, frequency |
| ADV ↔ `min_avg_value_20d_idr` | Other universe filters and fundamentals ("screen only") |
| | More enabled cards than `max_conditions`; more tickers than `max_portfolio_tickers` (P13) |

FACT: the prototype's `toBacktest` maps none of the 53 registry indicators (`audit/html_model.md` §2.4); it is replaced, not ported.

**Handoff.** The screener frame writes a one-shot `sessionStorage['edge-backtest-import']`:

`{v:1, source:'screener', definition:<the screen/v1 portable definition, canonical JSON>, definition_hash, evaluation_date, published_at, price_files:[{ticker, sha256}], mode, ticker|tickers, entry:{logic, at_least, window_bars, cards}, left_out:[{condition_id, condition:<the original wire object>, reason}]}`

It then posts `{type:'edge-nav', route:'backtest'}`. The shell accepts the message only when `event.origin === location.origin` and `event.source` is its own frame; no data travels in the message or the URL. Precedent: `edge-side-attach` and its Chromium test (`audit/edge_conventions.md` §4.1). The handoff carries the whole portable definition (universe filters, per-condition `within`, every left-out condition in its original form), not only the cards. The Backtest import keeps `definition` beside its cards in page state, so a later Backtest release that adopts more operators can take the left-out parts without the user rebuilding them (the user's follow-up: "nanti indikator di backtesting bisa kita tambahkan"). "Download JSON" saves the same object.

**Correction to the design (FACT).** The draft design's handoff carried the screener's `price_data_version` and compared it with the Backtest's. That comparison can never be equal: the screener's version covers all 845 tickers, while the Backtest's covers only the files it loads (`apps/backtest-worker/src/load.ts:22-23, 163`; `datafile.ts:271`). The handoff therefore carries the pack sha256 of each sent ticker (`price_files`); the import compares them with the files the page downloads and shows a "different data version" note on any mismatch.

**Backtest change: page only, on the page as EXEC-BACKTEST-LOAD left it.** FACT (main `010af1e`): `boot()` (`apps/edge-bff/backtest/src/app.ts:37-62`) asks for the catalog, draws on `PROVISIONAL` and calls `applyCatalog` only when the catalog answers within `QUICK_MS` (60 ms, line 34; checked at lines 50-51); otherwise `catalogArrived()` (`app.ts:67-85`) applies it later, and its defaults only while `edits.n === 0` (lines 68, 71). PROPOSED:
- `boot()` reads and deletes the key at its start, once, and holds the import; when the import names a ticker, that ticker is the one the first `load(tk, …)` asks for (line 54).
- One function applies the import, called from both paths: in `boot()` when the catalog came early, else in `catalogArrived()` after the catalog's defaults. It validates against the arrived catalog (`CAT.limits`), never against `PROVISIONAL`, and counts as an edit (`edits`, `state.ts`), so a later `catalogArrived()` keeps it.
- A new `src/import.ts` converts through `legacyCard`, registry defaults, `withinLimit` and core validation, and shows a toast naming what was left out.

**Untouched:** `backtest/src/core/*`, `apps/backtest-worker/**`, `backtest-registry.json`. **Prerequisites:** read `BACKTEST_END_TO_END.md` (now with §17) and `apps/edge-bff/backtest/CONTRACT.md` in full, and update CONTRACT §10 Page. Tests run with an early catalog and with a delayed one (the M253 lesson: a waiting state is tested with data that really arrives late; the EXEC-BACKTEST-LOAD smoke stub already delays).

| Card | |
|---|---|
| Need | The Backtest receives the same conditions and parameters, with nothing lost silently |
| Class | Translation between two condition dialects; lossiness must be explicit, and the limits come from the receiver |
| Fix and layer | Pure core translation + page-only import; the Backtest worker contract is unchanged |
| Covers | Registry indicators, core patterns, all-board flow, ADV; the full definition travels for a later Backtest release |
| Does not cover | Screener-only operators and data (listed as left out, kept in `definition`); more tickers or cards than the Backtest's limits |
| Risk and cost | The import must follow the page's asynchronous catalog (`app.ts:37-85`) |
| Verification | Losslessness property test: for every lossless kind, `evaluate(...)[at]` equals the Backtest `conditionSeries(calc, toBacktest(c))[at]` at every bar on fixtures; round trip definition → handoff → `definition` byte-identical under `canonicalJson`; lossy-list tests (`between`, mixed `within`, Regular flow); limits read from a catalog fixture; Chromium test frame → shell → Backtest frame with an early and a delayed catalog (TEST PLAN 10b.8) |
| Permanence | Permanent. The lossy list shrinks when the Backtest adopts more operators in its own release |

### 6.16 Security, limits and observability (Phase 19 of the brief)

**Never in the browser** (FACT patterns, `audit/edge_conventions.md` §5): DB URLs, bucket credentials, `TERMINAL_PROXY_KEY`, `SCREENER_WORKER_KEY`, internal hosts. Neither `/state` nor `/xsection` is in the browser allow-list; `/xsection` accepts only proxy-key callers, and `/state` grants no file. The worker holds no DB or bucket credentials. edge-bff accepts only a private host for the worker (the `apps/edge-bff/app/config.py:75-98` pattern). Presigned URLs and keys are never logged (the `terminal.ts` rule). Every store statement filters `owner_key`, every write uses `Depends(write)`, and names render as text.

**Limits.** Provisional values, replaced by Phase 17 measurements (P5): 20 active conditions, 8 universe metric filters, `within` ≤ 130 for technical metrics and flow maxima derived from the published window, lengths ≤ derived caps, compute budget from the cost model, worker deadline 20 s, one screen in flight per (owner, page) and at most `SCREENER_OWNER_INFLIGHT` running per owner in the worker, served round-robin across owners, worker queue 4, at most 50 definitions per counts request, response ≤ 2 MB JSON (INFERENCE; FACT: 845 × 5 values is 112 KB JSON / 37 KB gzip), and download and inflate caps per file and per refresh. Each worker limit is an environment variable with no default (6.17). Details in API CONTRACT §8.9. How these limits, the caches and the worker serve many users at once, and what that costs, is designed in MULTI-USER SCALE AND COST.

**Observability.** JSON logs with no secrets:
- **refresh:** `{data_version, published_at, files, bytes, granted, cached, grant_ms, download_ms, decode_ms, defaults_ms, integrity_failures, orphans, snapshot_digest, rss}`;
- **run:** `{definition_hash, data_version, owner_tag, replica, n_conditions, stages:[{name, in, out, ms}], conditions:[{id, source, cache, tickers_evaluated, cpu_ms}], pruned, queue_ms, total_ms, payload_bytes, status}` (`owner_tag` and `replica` feed the scaling triggers of MULTI-USER SCALE AND COST 6d.10).
`options.explain` returns the plan; the catalog shows the refresh state; `/health` reports snapshot age. An expensive request can therefore be explained from one log line.

### 6.17 Railway topology

**Dev only (the go of 2026-10-28, EXEC-SCREENER, is for dev, phase by phase); deploy outside 00:00-01:00 and 12:00-13:05 UTC (ERRORS M250); claim a deployment only at the exact deployment's SUCCESS.**

| Service | Change | Deploy |
|---|---|---|
| `screener-worker` (new; P3 a, decided) | 1 replica to start (scaling: MULTI-USER SCALE AND COST), `sfo`, private `http://screener-worker.railway.internal:8080`, restart ALWAYS, Railway healthcheck `/ready` (200 only with a loaded snapshot; timeout at least twice the measured cold start), `/health` for liveness and edge-bff's polling; no volume (a volume pins a service to one replica), `SCREENER_CACHE_DIR` on the container's disk; the availability floor (one or two replicas) is P32. Variables: `SCREENER_WORKER_KEY`, `TERMINAL_URL`, `TERMINAL_PROXY_KEY=${{terminal-api.TERMINAL_PROXY_KEY}}`, `SCREENER_FILE_ORIGIN` (the bucket origin `TerminalClient` checks, as `BACKTEST_FILE_ORIGIN`), `SCREENER_THREADS`, `SCREENER_CACHE_BYTES`, `SCREENER_CACHE_DIR`; limits `SCREENER_MAX_CPU_MS`, `SCREENER_CAP_BUDGET_MS`, `SCREENER_DEADLINE_MS`, `SCREENER_MAX_CONDITIONS`, `SCREENER_MAX_METRIC_FILTERS`, `SCREENER_WITHIN_MAX`, `SCREENER_MAX_COUNTS`, `SCREENER_MAX_RESPONSE_BYTES`, `SCREENER_QUEUE`, `SCREENER_MAX_FILE_BYTES`, `SCREENER_MAX_INFLATED_BYTES`, `SCREENER_MAX_REFRESH_BYTES`, `SCREENER_OWNER_INFLIGHT`, `SCREENER_PREVIOUS_GRACE_S`, with no defaults (backtest-worker convention, as `BACKTEST_MAX_DOWNLOAD_BYTES`). Memory starts at 2 GB, then is set to the measured peak × 1.5 | GitHub `main` (P3) |
| terminal-publisher | xsection writer and index | CLI, M248 procedure (below) |
| terminal-api | `/state` answer gains `xsection`; new `POST /xsection` | CLI, M248 procedure (below) |
| edge-bff | Routes, `SCREENER_WORKER_URL` / `SCREENER_WORKER_KEY` pair, the sub-app | GitHub `main` |
| backtest-worker, feature-04-worker, stockbit-updater, feature-01-worker | **None** | — |

**How the changes reach Railway (PROPOSED).**
- **The new service** is created through a pinned, reviewed IaC plan, the recorded method: FACT, a session's Railway token could not create a resource by CLI command, and ERRORS R29 names the pinned IaC plan as the way to create Railway resources from a session. First `railway config pull --force`, so the edge-bff variables set live on 2026-10-25 (`EDGE_TERMINAL_URL`, `TERMINAL_PROXY_KEY`, `RAILWAY_CHANGELOG.md:4594-4595`), which `.railway/railway.ts:189` lacks, enter the file. Then `railway config plan --verbose --out <file>`. The plan is applied with `railway config apply --plan <file>` only if its changes are the `screener-worker` service and the edge-bff `SCREENER_*` variables. FACT: two other drifts exist: the three legacy-service changes ERRORS R05 marks "do not apply" (applying redeploys them), and backtest-worker's `builder: "RAILPACK"` (`.railway/railway.ts:177`) against its recorded `DOCKERFILE` builds (`RAILWAY_CHANGELOG.md:4705`). If the plan shows either, it is not applied; the drift is reconciled in `railway.ts` and named in the review first (UNKNOWN until the plan is run). The pinned plan is recorded in `RAILWAY_CHANGELOG.md`.
- **CLI deploys** (terminal-api, terminal-publisher) follow ERRORS M248, whose class names these services: the last upload wins, in both directions. Merge the latest main into the branch; fetch main right before the upload and again after SUCCESS, and re-merge and re-upload if it moved; upload the repository layout (`git archive` of the app folder); compare the live build with the merged tree. Or merge to main first and CLI-deploy the merge commit (user decision N, 2026-10-27: one source, through a PR after E2E). FACT: terminal-api was last CLI-deployed from main `6f318ea` (`689dc465`, with `/state`); a branch tree without that commit would silently remove the route the backtest worker reads. `RAILWAY_CHANGELOG.md` records that a branch deploy can be overwritten.
- After any Railway change: update `.railway/railway.ts` and `RAILWAY_CHANGELOG.md`, then run `railway config pull --force` and `railway config plan` (AGENTS.md).

`SCREENER_FILE_ORIGIN` is added to the draft variable list because `TerminalOptions.fileOrigin` is required (`apps/backtest-worker/src/terminal.ts`, interface `TerminalOptions`).

### 6.18 Choices between the three candidate designs

The reliability design is the spine; parts of the performance and simplicity designs were grafted where their evidence was better.

| # | Topic | Resolution (PROPOSED) | Evidence |
|---|---|---|---|
| C1 | Price data source | Rack xsection files in the same publisher run | User wants one source ("Idealnya sih kalau ini menggunakan satu source, which is the same storage atau same rack", quoted at `apps/edge-bff/terminal/src/data/rack.ts:1-2`; EXEC.md EXEC-BACKTEST-LOAD K3, lines 8452-8453) and chose the rack schedule (`publisher.py:17-18`); per-ticker refresh costs 845-1,690 grants (`audit/benchmark.md` §4); a DB login or a separate cron creates a second time base |
| C2 | Preview data | Worker `POST /preview` pinned to the data version | No formula code in the page, no grant per click, no page/worker skew. Weighed against the shared rack loader (`apps/edge-bff/terminal/src/data/rack.ts`, EXEC-BACKTEST-LOAD K3 A: "satu pemuat rak untuk Backtest dan Terminal"; its header names later macro or cross-asset pages) for the one-ticker bars, with cells and markers from the worker. Not chosen now: each previewed ticker would be a `/bundle` grant on the shared gateway subscriber, whose default `tickers_per_hour` is 30 (migration `20261025_100:81`), so clicking through a result list would exhaust it for the Terminal and Backtest too; and the browser's latest `/bundle` can belong to a newer publication than the worker's snapshot during a refresh. The page reads no rack file, so it does not fork K3's loader. If the quota rule changes, the bars can move to `rack.ts` with the sha256 check of 6.15 |
| C3 | Flow ranking | Published F05 window + `flow.ts` | One top-N formula (`flow.ts:108-119`); no stockbit-updater coupling |
| C4 | Grant target | New NOLOGIN group for `terminal_publisher_login` only | `terminal_market_reader` also serves `terminal_api_login` (live L2) |
| C5 | Near-miss pruning | Near rows always computed | Pruning ALL at the second failure is cheap (0.35-0.56 s exhaustive) |
| C6 | `rs_rank` population | Fixed population (P7) | Ranks do not move with filter edits; planner-safe |
| C7 | Response shape | Rows, gzip | FACT (`audit/benchmark.md` §2c, 845 × 5 values): objects at 10 significant digits 27.5 KB gzip vs columnar 23.6 KB; full-precision objects 37.1 KB. Rows cost about 4 KB more at equal precision and keep the UI port and CSV simple. (The draft's "about 13 KB" compared full-precision objects with 10-digit columns.) |
| C8 | Screener core location | `apps/edge-bff/screener/src/core` | Outside `backtest/src/core`, so `engine_version` is unchanged; the page can import `contract.ts` and `universe.ts` (edge-bff build context `/apps/edge-bff`, `.railway/railway.ts:182`) |
| C9 | Where top-N generalises | Screener core, TEMPORARY (6.11) | A change to `flow.ts` changes the Backtest's `engine_version`; the general fix is a core release that generalises `flow.ts` |
| C10 | Brief: no daily rebuild vs in-memory recompute | The screener writes nothing; 8.1-10.2 s on one thread per publication (wall; first-repetition CPU 9.6-10.7 s) | Incremental exactness needs streaming state per indicator (P2) |
| C11 | Maximum `within` | 130 sessions (`SCREENER_WITHIN_MAX`) | The prototype's own marker window (`audit/html_model.md` §4.2) |


## PAGE LOAD SEQUENCE

New requirement (2) of the user, 2026-10-28: "Ada masalah sebelumnya terkait dengan seberapa lama FE displayed setelah browser dibuka. Jadi kamu feel free to lihat dan read bagaimana Terminal dan Backtest load its data to front end in terms of the sequence." (FACT: quoted in `EXEC.md` EXEC-SCREENER, history moved from PLAN.md, `EXEC.md:8475` onward at HEAD `88d3344`). This section describes, step by step, how the Terminal and the Backtest bring their data to the screen today (6c.1), then designs the Screener page's sequence on the same pattern (6c.2-6c.8). Everything in 6c.2 onward is **PROPOSED** unless a line carries another label.

**State of the repository (FACT).** While this report was revised, the branch moved from `ad7ba34` to HEAD `88d3344`, which adds `EXEC.md` EXEC-SCREENER: the user's "go" of 2026-10-28, P4 sub-choice A (cells whose lookback crosses an ex-date are **shown** with a remark, not blanked) and the lifting of the two-agent limit (`EXEC.md:8477-8488`). Later commits of the EXEC-SCREENER work in progress (`8a236eb`, `1b6dcc1`) add only the new scaffold `apps/edge-bff/screener/` under `apps/` and `.railway/` (`git diff --name-only 010af1e HEAD -- apps .railway`, checked 2026-10-28), so every other `apps/` and `.railway/` citation below holds at main `010af1e` and at HEAD. Documentation lines are cited at HEAD.

Labels and evidence notation as in TARGET ARCHITECTURE. Report sections are cited by name (TARGET ARCHITECTURE §6.x, API CONTRACT §8.x, FRONTEND INTEGRATION §9.x, PERFORMANCE EVIDENCE §11.x, PERFORMANCE BENCHMARK PLAN §11b.x, TEST PLAN §10b.x).

### 6c.1 How the Terminal and the Backtest load today (FACT)

#### 6c.1.1 The EDGE shell (common to every framed page)

| Step | What happens | Evidence |
|---|---|---|
| H1 | The browser asks `/terminal` or `/backtest`. edge-bff answers `static/index.html`, 473,432 bytes at HEAD. The middleware sets `Cache-Control: no-store` on every answer that sets no header of its own, and the app has no compression middleware (103,243 bytes once gzipped locally), so the shell document is downloaded again, uncompressed by the app, on every open. Whether Railway's edge compresses it is UNKNOWN (check: `curl -sI -H 'Accept-Encoding: gzip' https://<edge-bff>/terminal` and read `content-encoding`) | `apps/edge-bff/app/main.py:236, 283-290`; `wc -c`, `gzip -c` on HEAD; grep finds no `GZip` in `main.py` |
| H2 | The shell's three scripts `edge-client.js`, `edge-labels.js`, `edge-view.js` load; `frontend_script` sets no cache header, so they are no-store too | `apps/edge-bff/static/index.html:10289-10291`; `main.py:303-307` |
| H3 | `App` shows "Checking session…" until `Edge.session()` resolves. `Edge.session()` is `GET /api/v1/auth/session`, then a wait of up to 3 s for `GET /api/v1/models` (the chat's model list, read "before the work page shows"). edge-bff keeps that list 600 s | `index.html:12434, 12460`; `apps/edge-bff/static/edge-client.js:8-9, 115-123`; `main.py:54, 558-574` |
| H4 | Only then does the route render the frame: `<iframe class="terminal-frame" src="/terminal-app/">` or `"/backtest-app/"`. INFERENCE: the render switch holds one page element per path, so leaving the route removes the frame and coming back boots the frame page again | `index.html:10796-10808, 12460` |
| H5 | The frame document (`/terminal-app/`, `/backtest-app/`) is no-store; its hashed assets are `public, max-age=31536000, immutable`, so after the first visit the script and style come from the browser cache. Both frame pages load Google Fonts with a render-blocking stylesheet in their head | `main.py:333-345, 349-361`; `apps/edge-bff/terminal/index.html:7`; `apps/edge-bff/backtest/index.html:9-10` |

#### 6c.1.2 Terminal (`apps/edge-bff/terminal`)

| Step | What happens | In parallel? | Evidence |
|---|---|---|---|
| T1 | `boot()`: the side panels take the state the user left (closed by default); an open panel and the chart show the shared ring ("Loading MAPI"); `mark('page script')` | — | `terminal/src/main.ts:117-146` (ring 136-141); ring markup `terminal/src/ui/spin.ts:4` |
| T2 | `liveData()`: `GET /api/v1/auth/session` first, for the CSRF token of the POSTs | Sequential, first | `terminal/src/data/live.ts:149-151, 71-76` |
| T3 | Then together: the three reference lists (`/reference/tickers`, `brokers`, `logos`: each a presigned URL, then a bucket download **without** sha256, so never browser-cached) and `POST /bundle {ticker, datasets:[price, broker, events], packs:true}` for the remembered ticker | Yes, 4 requests | `live.ts:152-160`; ERRORS "EXEC-TERMINAL-SPEED — selesai", "Belum" (`ERRORS_AND_SOLUTIONS.md:2307-2308`) |
| T4 | The ticker list is awaited before the remembered symbol is accepted; the guessed `/bundle` is used when the symbol is known | Waits for the ticker list | `live.ts:161-165` |
| T5 | One Web Worker downloads every file of the bundle at once. Each file is read from IndexedDB `terminal-files` by sha256 first, else downloaded (asked again on a 5xx or a cut-off body) and stored when its bytes hash to the announced sha256 (50 MB, least recently used first) | Yes, all files at once | `live.ts:96-128`; `terminal/src/data/worker.ts:30-48, 103-116`; `terminal/src/data/rack.ts:15-17, 29-97` |
| T6 | The worker answers in stages: `price` as soon as the price pack is read, then `broker` (the last two years), `events`, then `brokerAll` (every year) and per-file `stats` | Staged | `worker.ts:112-132` |
| T7 | On `price` the chart is drawn (`mark('chart drawn')`); `later()` fills the Flow Timeline with the recent years, then with every year; Broker activity is drawn only when its panel is open; IHSG is asked only when Relative performance draws | Staged, on demand | `main.ts:89-102, 144`; `live.ts:179-186, 198` |
| T8 | A timeframe change reloads the page; its files then come from the browser cache | — | `main.ts:33-47` |
| T9 | `?perf=1` shows each stage mark and each file's time, size and cache hit | — | `terminal/src/app/perf.ts:1-35` |

#### 6c.1.3 Backtest (`apps/edge-bff/backtest`, after EXEC-BACKTEST-LOAD and EXEC-BACKTEST-SPIN)

| Step | What happens | In parallel? | Evidence |
|---|---|---|---|
| B1 | `boot(liveApi())`; the shared ring stylesheet is imported from the Terminal | — | `backtest/src/main.ts:3, 7` |
| B2 | Palette, builder width and panel state from `localStorage` (`ml.bw`, `ml.panel`) | — | `backtest/src/app.ts:38-40`; `backtest/src/layout.ts:12, 31` |
| B3 | `GET /api/v1/backtests/catalog` is asked at once (a GET carries the cookie and needs no CSRF), and the page switches to `PROVISIONAL`: no stocks, brokers, groupings or dates, the core's ceilings as limits, flow taken as available | Starts first | `app.ts:46-48`; `backtest/src/api/live.ts:44-46, 160`; `backtest/src/env.ts:17-22` |
| B4 | The catalog is used for the first render only if it answers within `QUICK_MS` = 60 ms | Waits ≤ 60 ms | `app.ts:34-35, 49-51` |
| B5 | The shown ticker's bars start: `load()` → `bars()` → one `POST /bundle` (price, plus broker when a flow card needs it), preceded by one memoised `GET /api/v1/auth/session` for the CSRF token; the files are checked and decoded in `api/load.worker.ts` through the same `rack.ts` cache and download | Yes, beside the catalog | `app.ts:54-56`; `env.ts:44-53`; `live.ts:21-28, 64-78, 138-146`; `api/load.ts:14-38`; `api/load.worker.ts:7-17` |
| B6 | After at most 60 ms more, the listeners are bound and builder, chart, signals and results are drawn. Parts that need the catalog say so ("Loading …" options); the chart is emptied and shows the ring "Loading <TICKER>" until its prices are there; flow lanes show a small ring until the broker data arrives | First paint | `app.ts:56-59`; `builder.ts:170`; `signals.ts:80-105, 149-153, 187-191` |
| B7 | When the catalog arrives later, `catalogArrived()` applies its defaults only if the user has edited nothing (`edits.n === 0`), and does not redraw a builder field that has the focus until it loses it | — | `app.ts:60, 64-85` |
| B8 | Server side: edge-bff keeps the worker's catalog 60 s; the worker keeps it per publication (`ByPublication`, built at start, rebuilt only on a new `/state` `finished_at`) | — | `apps/edge-bff/app/backtest.py:44, 1056-1070`; `apps/backtest-worker/src/catalog.ts:54-81` |

#### 6c.1.4 Measured timings (FACT)

All page timings were taken from the sandbox (not from Indonesia) with `verification/backtest/page_timing_dev.py`: Playwright signs in, opens the EDGE route in a new browser context (cold), then in a second page of the same context (warm: the IndexedDB file cache is kept), records every request with its start time and a long-task observer, and takes "ready" when every Run button is enabled, which happens at the first render (`page_timing_dev.py:1-4, 17-21, 79-101`; `app.ts:58`).

| Page | Measure | Value | Evidence |
|---|---|---|---|
| Backtest, before EXEC-BACKTEST-LOAD | First open until menus and Run usable; second open; longest main-thread block (open; switch to BBRI) | 8.83 s; 2.36 s; 0.53 s; 0.97 s | `BACKTEST_END_TO_END.md:686-689` |
| Backtest, after | Same measures | 1.37 s; 1.12 s; no block over 50 ms | `BACKTEST_END_TO_END.md:686-689`; `RAILWAY_CHANGELOG.md:4919-4920` |
| Backtest catalog | Worker `/v1/catalog` per build, before → after | 3.5-4.0 s → about 0.25 s (first catalog 2.2 s, then 0.24-0.29 s through edge-bff) | `BACKTEST_END_TO_END.md:688`; `RAILWAY_CHANGELOG.md:4911-4912` |
| Backtest candles, live check after EXEC-BACKTEST-SPIN | Chart ring gone (candles drawn) | 3.9 s from the sandbox | `RAILWAY_CHANGELOG.md:4925-4926` |
| Terminal, same harness, 2026-10-27 | Chart, first open; second open | 2.28 s; 1.77 s (2.74 s before EXEC-BACKTEST-LOAD) | `BACKTEST_END_TO_END.md:686-687`; `ERRORS_AND_SOLUTIONS.md:2881` |
| Terminal, `?perf=1`, 2026-10-26 | Second visit ANTM: chart | 2.5 s, of which 2.2 s waiting for the ticker list and `/bundle` | `PLAN.md:888-889` |
| Terminal, local edge-bff, files from the test cache | Chart drawn | 1.9 s; longest long task 414 ms (first paint of about 2,100 bars) | `verification/terminal_api/FRONTEND_ARCHITECTURE.md:117-119` |
| Session check after the edge-bff pool | `GET /api/v1/auth/session` median | 221 ms, against 217 ms for a static file from the sandbox | `RAILWAY_CHANGELOG.md:4917-4918` |
| Bucket objects | Time to first byte per object; protocol | 0.72-1.42 s; HTTP/1.1, at most 6 connections per host. Railway's edge (HTTP/2) sent 203 KB in 0.27-0.54 s | `ERRORS_AND_SOLUTIONS.md:2263-2281` (M240) |
| `/bundle` under concurrency | 20 concurrent, packs | median 0.53 s, max 0.71 s | `ERRORS_AND_SOLUTIONS.md:2302-2303` |
| From the user's location | `?perf=1` from Indonesia | Never received | `ERRORS_AND_SOLUTIONS.md:2307` |

**Lessons on record (FACT).**
- The next rack pages (macro, cross-asset) use `rack.ts` and the same pattern: draw first, load when needed, decode in a Web Worker, keep derivations per publication (`ERRORS_AND_SOLUTIONS.md:2899-2900`).
- Every new waiting state is tested with data that really arrives late, and the live page is checked right after the deploy (M253, `ERRORS_AND_SOLUTIONS.md:2918-2932`).
- One loading ring for every rack page; the chart is emptied while a new ticker loads (EXEC-BACKTEST-SPIN, `ERRORS_AND_SOLUTIONS.md:2902-2916`; `EXEC.md:8464-8473`).
- TERMINAL-CACHE-FIRST (approved into the plan 2026-10-26, not built): draw the chart from the browser cache first and update it quietly with an "updating" mark; open question whether old data may show before the session is checked, because of shared devices (`PLAN.md:879-896`).

**What the timings say (INFERENCE).**
- The Backtest's 1.37 s is shell + session + model list + frame + first render on `PROVISIONAL`: it waits for no market data. The Terminal's chart waits for the session, the ticker list and the bucket objects (T2-T6); the bucket's per-object latency (M240) is the largest single part, which is why it stays at 1.8-2.3 s.
- A page that renders server answers from edge-bff memory, and fetches no bucket object, can reach its first real content at about the Backtest's first render plus one round trip to edge-bff (about 0.22-0.29 s from the sandbox, rows above).
- The shell's wait for the model list (H3) and its no-store, uncompressed document (H1) sit in front of every framed page; their cost was never measured separately (UNKNOWN; check in 6c.8).

### 6c.2 Screener design premises (FACT from the design, cited)

- Thin client: the page holds no formula code, reads no rack file and fetches only from its own origin (`connect-src 'self'`); screens, previews and counts are computed by `screener-worker` (FRONTEND INTEGRATION §9.1, §9.3; TARGET ARCHITECTURE §6.18 C2).
- The worker builds one snapshot per publication: the 53 defaults, universe attributes, default ranks and every preset's match and near counts (TARGET ARCHITECTURE §6.7). edge-bff keeps the last catalog and universe in memory keyed by (`price_data`, `screener_registry`) and checks the worker's `/health` at most every 60 s (API CONTRACT §8.4).
- Every worker answer carries `versions` and `data` (`price_data`, `screener_engine`, `screener_registry`, `published_at`, `refresh`) (API CONTRACT §8.3).
- Saved screens, My metrics and one watchlist live in `edge_bff` tables (P12 (a), decided 2026-10-28, `EXEC.md:8485-8486`); the browser keeps only conveniences under `scr.*` (TARGET ARCHITECTURE §6.14).
- Stale tickers and tickers with a price break are hidden by default; shown through the filter, their rows carry a remark and their price-derived cells keep their value with the remark (P4, sub-choice A, `EXEC.md:8483-8485`).
- The prototype opens with the preview closed and an empty screen, and evaluates all 26 presets at boot for their counts (`audit/html_ui.md` §1, §3.13); the table pages 25 rows at a time (`audit/html_ui.md` §2, `perPage`).

### 6c.3 What the browser can draw at once, and from where (PROPOSED)

| Item | Where it lives | Key | Drawn when | Evidence or reason |
|---|---|---|---|---|
| Frame document (layout of the prototype: page head, universe bar, preset tabs, builder, results header, closed preview) with static loading rings in each data area | Not cached (no-store, as both frame pages) | — | First paint, before the script runs | The house rule `main.py:236`; the rings in static markup show even before the IIFE executes (INFERENCE) |
| Script and stylesheet | Browser HTTP cache | Hashed file name, `immutable` | From the second visit, with no request | Same route pattern as `main.py:340-345` |
| Theme, panel sizes, preview open or closed, the last open screen (its draft definition and, if saved, its `item_id`) | `localStorage` (`edge-auth-monitor-theme`, `scr.*`) | — | Synchronously in `boot()`, before any request | Per-viewer conveniences (TARGET ARCHITECTURE §6.14; FRONTEND INTEGRATION §9.5) |
| Last catalog, last universe, last result of the last open screen (the JSON bytes of each answer) | IndexedDB `terminal-files` through `rack.ts` `fileCache()` | sha256 of the bytes, which edge-bff sends as the `ETag` | After the first authenticated answer of this page load (6c.4 S3) | Reuse of the shared browser cache (`rack.ts:29-70`); only bytes whose sha256 equals the announced value are stored, as `worker.ts:40` |
| Pointer to those bytes | `localStorage scr.boot` = `{login, versions, published_at, catalog_sha, universe_sha, last:{definition, definition_hash, result_sha}}` | — | Read in `boot()`; replaced after each answer | Keeps the cache content-addressed: a pointer for another login is dropped at boot, so its bytes are never read again and age out of the LRU |

Per-user objects (saved screens, watchlist) are never drawn from browser storage: they come from the server on every load (6c.4 S2).

### 6c.4 The boot sequence (PROPOSED)

Times are budgets from the measurements of 6c.1.4, not measurements (INFERENCE).

| Step | What happens | Waits for | In parallel with | Budget |
|---|---|---|---|---|
| S0 | Shell H1-H4, unchanged | — | — | Part of the Backtest's 1.37 s / 1.12 s |
| S1 | Frame first paint from static markup: the whole layout, each data area with the shared ring ("Loading indicators", "Loading presets", "Loading results", "Loading data status"); controls that need the catalog are visibly inactive, as the Backtest's `PROVISIONAL` parts | Frame HTML and the cached bundle | — | ≤ 1.4 s cold, ≤ 1.2 s warm from navigation |
| S2 | `boot()` reads `scr.*` and `scr.boot` and sends at once: `GET /api/v1/auth/session` (CSRF); `GET catalog` and `GET universe`, each with `If-None-Match: <cached sha>` when the pointer has one; `GET items?kind=screen`; `GET watchlist`. GETs need only the cookie (the Backtest's catalog GET, B3) | — | All five together | One round trip, about 0.22-0.29 s |
| S3 | **Cached paint.** On the first authenticated answer (any 2xx or 304), the page draws from IndexedDB what the pointer names: the catalog (builder, adder, preset tabs with their counts), the universe (bar counts, "In universe X of N") and, for the last open screen, its result, when the result's `versions` equal the cached catalog's. The data line shows "Updating…" with the ring until S4 confirms. Nothing cached is drawn before an authenticated answer, so a frame opened outside the shell (`/screener-app/` is served without a session, as `/terminal-app/`, `main.py:333-338`) shows no data to a signed-out browser | S2's first answer | — | ≤ 0.3 s after S2 |
| S4 | **Confirmation.** `304` on catalog and universe: the cached copies are current; "Updating…" goes. `200`: the new bytes replace the drawing; the page drops every pointer whose `versions` differ and stores the new bytes when they hash to the `ETag` | S2's catalog and universe | — | Same round trip |
| S5 | **First results.** An empty screen (first visit, or the last screen had no condition) needs no run: its rows are the universe rows after `universe.ts`, the same function the worker applies in stage S0 (API CONTRACT §8.4). The default hides stale and price-break tickers (P4). A screen with conditions whose cached result matched in S3 and whose versions S4 confirmed needs no run either: the result is fixed by (`price_data`, `screener_engine`, `screener_registry`, `definition_hash`) (API CONTRACT §8.10). Otherwise `POST run` is sent as soon as the CSRF token is there | Session (CSRF) for a run | Catalog and universe | Empty screen: first rows ≤ 1.8 s cold, ≤ 1.4 s warm. Run: the worker's answer (6c.7) |
| S6 | Saved screens and watchlist fill their places when they answer (the My screens tab, the watch stars). They never block S5 | S2 | — | — |
| S7 | **Waits until asked:** the preview (only on a row click or a lookup; `POST preview`, debounced, pinned to `data_version`); "Stock vs IHSG" (from the preview's answer); `POST counts` for the saved screens (only while the My screens tab is open, at most 50 definitions, cached per (`price_data`, `definition_hash`)); CSV (local); Send to Backtest (reads `GET /api/v1/backtests/catalog` only when its dialog opens, TARGET ARCHITECTURE §6.15) | User action | — | Preview ≤ 1 s p95 through edge-bff (PERFORMANCE BENCHMARK PLAN §11b.5) |
| S8 | **Edits.** Condition and parameter edits are debounced 350 ms and sent with `client_order {page, seq}`; the page aborts its previous `run` fetch (the Backtest's `preview.ts` pattern, `backtest/src/preview.ts:1-12, 58`), and edge-bff's `unless_gone` then cancels the worker call (the `backtest.py:971-1000` pattern). Sort, page, search, near toggle and CSV never call the server (FRONTEND INTEGRATION §9.7) | — | — | Run answer per 6c.7 |

Preset counts reach the page with the catalog (S3/S4), computed once per publication by the worker, never by 26 screens in the browser (TARGET ARCHITECTURE §6.7). PROPOSED addition: the worker also keeps each available preset's full result in its result cache from the refresh onward (the counts computation evaluates them anyway), so a preset click is a cache hit: about one round trip.

**What runs on the server at a page open (PROPOSED).** A first visit costs two answers from edge-bff memory (catalog, universe) and a session lookup; a repeat visit on the same publication costs two `304`s. Neither reaches the worker's compute or PostgreSQL's market tables. Only a remembered screen with conditions and a result that is not current reaches the worker, and its answer is shared through the result cache (MULTI-USER SCALE AND COST §6d.2).

### 6c.5 Versions and cache invalidation (PROPOSED)

1. **One version source per page load.** The catalog's `versions` and `data.published_at` are the page's current version. A cached object is used only when its stored `versions` equal them field by field (`price_data`, `flow_data`, `screener_engine`, `registry`, `screener_registry`).
2. **A new publication** changes `price_data` (and `published_at`, the rack's `finished_at`). On the next catalog answer the page drops every pointer at the old version; the old bytes are never read again and age out of the 50 MB LRU (`rack.ts:16, 64-66`).
3. **An answer newer than the catalog.** If a `run` or `preview` answer carries a `price_data` other than the page's catalog, the page asks the catalog again (`If-None-Match`) and redraws the preset counts and the data line; the preview keeps its 409 `DATA_VERSION_CHANGED` rule and the page re-runs the screen (API CONTRACT §8.6), so chart and table never mix publications.
4. **edge-bff's cache follows the worker without waiting.** Besides its 60 s `/health` check (API CONTRACT §8.4), edge-bff drops its cached catalog and universe as soon as any worker answer carries a `price_data` other than theirs. PROPOSED change to API CONTRACT §8.4: it narrows the window in which edge-bff serves the previous catalog after a swap from up to 60 s to one request.
5. **Conditional requests.** edge-bff answers `GET catalog` and `GET universe` with `ETag: "<sha256 of the JSON bytes>"` and honours `If-None-Match` with `304` and no body. The house `Cache-Control: no-store` stays (`main.py:236`), so the browser's HTTP cache is never used; the page sends `If-None-Match` itself from its pointer. PROPOSED change to API CONTRACT §8.4, which today gives the `ETag` only "so the page can skip a re-render".
6. **Engine or registry release.** A new `screener_engine` or `screener_registry` changes `versions` and invalidates the same way. A saved screen whose parameter left the registry range shows "needs review" (API CONTRACT §8.7); nothing is adjusted.

### 6c.6 Loading and failure states (PROPOSED)

All rings are the shared component (`terminal/src/ui/spin.ts:4`, `terminal/src/styles/spin.css`; 0.15 s per turn, 1.6 s with reduced motion, `EXEC.md:8467-8468`).

| State | What the page shows | What it does |
|---|---|---|
| Before any answer | Static rings in each data area; catalog-dependent controls inactive | — |
| Cached paint, not yet confirmed | The cached content and "Updating…" with a ring beside the data line | Replaced or confirmed by S4 |
| Run in flight | Results body: ring "Running screen"; the previous result stays visible and is marked out of date (as the Backtest's "Out of date" tag on a stale result, `backtest/src/builder.ts:120-134`) | Aborted when a newer edit is sent |
| Preview loading | Chart emptied, ring "Loading <TICKER>" (EXEC-BACKTEST-SPIN rule S1 A) | Never shows the previous ticker's candles |
| 401 | "Sign in to EDGE first, then open the Screener tab again." (wording of `backtest/src/api/live.ts:17`) | No retry; cached data stays hidden |
| 503 `SCREENER_NOT_READY` with `Retry-After` | "The screener is starting; it retries in N s" with a ring | Retries after `Retry-After`; the cached paint stays, marked with its date |
| 503 `SCREENER_DISABLED` | "The screener is switched off on this environment" | No retry |
| 503 `SCREENER_UNAVAILABLE`, network error | "The screener service cannot be reached; retry shortly" and a Retry button | One automatic retry after 2 s, then the button |
| 424 `DATA_UNAVAILABLE`, `DATA_INTEGRITY` | The API CONTRACT §8.8 message; with a previous version the catalog shows `failed_keeping_previous` and the page keeps working on it | No retry until the next catalog answer |
| 409 `BUSY` | "The screener is busy; retrying" with a ring | Retries twice with 1 s and 2 s backoff, then the message and a Retry button |
| 409 `SCREEN_REPLACED`, `PREVIEW_REPLACED` | Nothing | Ignored (a newer answer follows) |
| 504 `TIMEOUT`; 422 `LIMIT_EXCEEDED {limit:"compute_budget", costliest}` | The message naming the costliest condition and the fix (API CONTRACT §8.8) | No retry |
| IndexedDB unavailable or blocked | Nothing visible: the page loads without the cached paint | `fileCache()` already turns every IndexedDB failure into "no cache" (`rack.ts:26-47`) |

Every refusal above already has its rule, how to pass it, examples and message in API CONTRACT §8.8-8.9 (the AGENTS.md "Gates and evidence" rule); the page only renders them.

### 6c.7 Targets (PROPOSED; the user may change them)

| Milestone | Definition, as the timing script reads it | Cold | Warm | Grounding |
|---|---|---|---|---|
| Frame first paint | The frame's layout with its rings is visible (an attribute `data-boot="skeleton"` on the app root) | ≤ 1.4 s | ≤ 1.2 s | Backtest first render 1.37 s / 1.12 s, same shell (FACT, 6c.1.4) |
| First results, empty screen | The first table row and the data line with `evaluation_date` (`data-boot="results"`) | ≤ 1.8 s | ≤ 1.4 s | First paint + one edge-bff round trip of about 0.25 s (FACT, Backtest catalog through edge-bff); below the Terminal's chart (2.28 s / 1.77 s) because no bucket object is on the path (INFERENCE from M240) |
| First results, remembered screen with conditions | Same, after its run or its cached result | ≤ first paint + 0.3 s + the run's p95 (default-only ≤ 0.5 s, mixed ≤ 2 s) | ≤ 1.4 s when the cached result is current (no run) | PERFORMANCE BENCHMARK PLAN §11b.5 S1, S5 |
| Main thread | Longest task during boot and first render | none over 50 ms | none over 50 ms | Backtest after EXEC-BACKTEST-LOAD (FACT, 6c.1.4) |
| Preview | Row click to chart drawn | ≤ 1 s p95 | — | §11b.5 S16 |
| New publication visible | Time from the rack's `finished_at` to a page open showing the new `published_at` | ≤ the worker's refresh (≤ 2 min, §11b.5 S14) + one request (6c.5 item 4) | — | — |

Measured from the sandbox like the Backtest; the user's own location is asked once through `?perf=1` (the Terminal never received it, 6c.1.4).

**No Web Worker for decoding (PROPOSED, INFERENCE).** The page's largest answers are small: a whole-universe result of 845 rows × 5 values is 112 KB JSON / 37 KB gzip (FACT, PERFORMANCE EVIDENCE §11.5); the universe is about 845 rows (INFERENCE about 20-35 KB gzip); the generated registry the catalog builds on is 42,440 bytes, 3,306 gzipped (FACT, `apps/edge-bff/backtest/src/core/backtest-registry.json`, measured on HEAD). The table draws 25 rows a page. A Web Worker is added only if the timing script records a long task over 50 ms in parsing or sorting; if one is ever added, it is a parse worker, not a second rack loader.

### 6c.8 Reuse, and what is new

| Code | Use in the Screener | Kind |
|---|---|---|
| `terminal/src/ui/spin.ts`, `terminal/src/styles/spin.css` | Every ring | Reused as is (imported, as the Backtest does, `backtest/src/main.ts:3`, `signals.ts:18`) |
| `terminal/src/data/rack.ts` `fileCache()`, `sha256Hex()` | Browser cache of catalog, universe and last result bytes, keyed by sha256 = `ETag`, in the shared `terminal-files` store and its 50 MB LRU | Reused as is |
| `terminal/src/app/perf.ts` `mark()` | `?perf=1` stage marks (`page script`, `session`, `catalog`, `universe`, `results from cache`, `results`, `preview`). Its `performance.mark` names carry the prefix `terminal:` (`perf.ts:28`), which the timing script reads | Reused as is |
| `backtest/src/app.ts` `within()` / `QUICK_MS`, `env.ts` `PROVISIONAL` | The rule "draw at once, use an answer only if it is early, apply a late catalog only while nothing was edited" | Pattern reused; the helpers are module-private, and exporting them would change the Backtest page bundle |
| `backtest/src/api/live.ts` `csrf()` and `call()` error mapping; `backtest/src/preview.ts` latest wins with `AbortController` | The Screener's `api/live.ts` | Pattern reused. FACT: the session/CSRF helper already exists twice (`terminal/src/data/live.ts:71-76`, `backtest/src/api/live.ts:21-28`); a shared module is a later clean-up that touches both pages (P27) |
| `rack.ts` `fetchFile`, `backtest/src/api/load.ts`, `api/load.worker.ts`, `terminal/src/data/worker.ts` | Not used: the page reads no rack file (TARGET ARCHITECTURE §6.18 C2). If the preview's bars ever move to the rack, these are imported, not copied | Not used now |
| `verification/backtest/page_timing_dev.py` | Template for `verification/screener/page_timing_dev.py` | Pattern reused |
| `apps/edge-bff/screener/src/app.ts` `boot()`, `api/live.ts` (ScreenerApi), `api/boot-cache.ts` (pointer and version check over `fileCache`) | The sequence of 6c.4-6c.6 | New |
| edge-bff `app/screener.py`: `ETag` / `If-None-Match` / `304` on catalog and universe; cache drop on a newer worker version; worker answers relayed as gzip bytes (MULTI-USER SCALE AND COST §6d.5) | Server side of 6c.5 | New |

### 6c.9 How it is verified (PROPOSED)

1. **`verification/screener/page_timing_dev.py`** (read-only, same structure as `verification/backtest/page_timing_dev.py`: credentials into memory, never printed; long-task observer; cold context, then a warm page in the same context):
   - times frame first paint, first results and network quiet for (a) an empty screen and (b) a remembered screen with conditions, cold and warm;
   - asserts from the request log that the S2 requests start within 50 ms of each other, that no request goes to `*.t3.storageapi.dev`, and that the warm open of the same publication gets `304` for catalog and universe and sends no `run` when the cached result is current;
   - records the shell's own costs (H1 document bytes and `content-encoding`, the `/api/v1/models` wait) so the EDGE-wide items P25 and P26 can be judged;
   - times the routes directly with the same session: session, catalog, universe, `run` S1 and S5 definitions, `preview`;
   - writes `report.json` and screenshots; results recorded in `verification/screener/PAGE_TIMING.md` with the deployment IDs and the publication's `finished_at`.
2. **Page smoke with late data (M253 lesson)**, in the smoke build: a slow session; a slow catalog (1.5 s); a slow run (3 s); 503 `SCREENER_NOT_READY` with `Retry-After: 2`, then ready; a cached paint followed by a `200` with a new version (the drawing is replaced and "Updating…" goes); a run answer newer than the catalog (the catalog is asked again); IndexedDB refusing to open (the page works without cache); five edits within 350 ms (one run answered and drawn, the earlier fetches aborted). Pass: the page answers to input throughout, and no long task over 50 ms.
3. **Unit tests** of the pointer: another login's pointer is dropped; a pointer at other `versions` is never drawn; bytes whose sha256 differs from the `ETag` are not stored.
4. **Live check right after each deploy** (M253): one cold and one warm open with the timing script before any other work.

These add rows to TEST PLAN §10b.12 and a page scenario to PERFORMANCE BENCHMARK PLAN §11b.3 (Consequences below).

### 6c.10 Consequences for other sections (PROPOSED; agent A owns those files)

- API CONTRACT §8.4: `ETag` = sha256 of the JSON bytes, `If-None-Match` → `304`; edge-bff drops its cached catalog and universe on a worker answer at another `price_data` (6c.5 items 4-5).
- API CONTRACT §8.10: a browser row (IndexedDB `terminal-files` through `rack.ts`, key sha256, pointer `scr.boot`, invalidated by `versions`).
- FRONTEND INTEGRATION §9.1: "`rack.ts` and the Web Worker decode do not apply" becomes: `rack.ts` `fileCache`/`sha256Hex` are reused for the answer cache; no Web Worker and no rack download.
- TARGET ARCHITECTURE §6.7: pre-warm the result cache with each available preset's full result.
- TEST PLAN §10b.12 and PERFORMANCE BENCHMARK PLAN §11b.3, §11b.5: the timing script, the late-data smoke and the targets of 6c.7.

### 6c.11 Unknowns (UNKNOWN, with the check that settles each)

| # | Unknown | Check |
|---|---|---|
| L-U1 | Whether Railway's edge compresses edge-bff answers (the app does not) | `curl -sI -H 'Accept-Encoding: gzip'` on `/terminal` and on a JSON route; read `content-encoding` |
| L-U2 | The cost of the shell's model-list wait (H3) and of the 473 KB no-store document (H1) on a cold open | The timing script's request log (6c.9 item 1) |
| L-U3 | Real sizes of the catalog and universe answers | First dev build: bytes in the timing script's log |
| L-U4 | Timings from Indonesia | One `?perf=1` reading from the user |
| L-U5 | Whether the first paint happens before the classic script at the end of `<body>` executes on a cold visit | Chromium trace (first-contentful-paint against script evaluation) in the timing script |

### Decisions for the user

Provisional ids; agent A assigns the final numbers.

- **P24 — Cached paint of Screener answers.** May the page draw its last catalog, universe and last result from the browser cache before the server confirms them? Options: (a) yes, but only after the first authenticated answer of the page load, marked "Updating…" until confirmed (6c.4 S3); (b) yes, at once, before any answer (faster by one round trip, about 0.25 s, but a frame opened directly while signed out would show the last data on a shared device); (c) no browser cache: draw only server answers. Recommendation: (a). It answers, for the Screener, TERMINAL-CACHE-FIRST's open question in its safe form (`PLAN.md:895-896`), and saves a run on every repeat visit within a publication.
- **P25 — EDGE shell: framed pages wait for the chat's model list.** Every open of Terminal, Backtest and Screener waits for `/api/v1/models` (up to 3 s) before the frame is created (H3). Options: (a) the shell renders the frame routes once the session answers and reads the model list in the background; (b) keep it. Recommendation: measure first (6c.9, L-U2); if it costs more than 100 ms on a cold open, (a), as an EDGE-wide item outside the Screener phase.
- **P26 — EDGE shell document: no-store and uncompressed.** The 473 KB shell is downloaded on every open (H1). Options: (a) compress answers in edge-bff (gzip for HTML, JS and JSON) and give the shell scripts a revalidating cache policy; (b) keep it. Recommendation: settle L-U1 first; then (a) as an EDGE-wide item. Not part of the Screener phase.
- **P27 — One session/CSRF helper for every framed page.** The helper exists twice today and the Screener would add a third copy (6c.8). Options: (a) a shared module now, which changes the Terminal and Backtest bundles and needs their 1:1 and smoke checks; (b) a third copy now, a clean-up item later. Recommendation: (b), to keep the Screener phase off the other pages.
- **P28 — Page-load targets.** Accept the targets of 6c.7 as the acceptance criteria of the Screener page (or give others).


## MULTI-USER SCALE AND COST

New requirement (1) of the user, 2026-10-28: "Also, ini nanti akan multiuse,r jadi infrastruktur harus bisa di scale UP + efficient cost wise." (FACT: `EXEC.md:8547-8548`; listed as "Syarat baru (1)" at `EXEC.md:8560`, and "desain multi-user" is part of Phase 1 at `EXEC.md:8490`). This section states what EDGE is today for several users (6d.1), then designs how the Screener serves many users at low cost: what is computed once and shared (6d.2), what is per user (6d.3), how `screener-worker` and edge-bff scale out (6d.4, 6d.5), concurrency and fairness (6d.6), the terminal-api account (6d.7), what EDGE itself still needs (6d.8), a cost model (6d.9), scaling triggers (6d.10) and what Phase 17 measures to set them (6d.11). Everything from 6d.2 onward is **PROPOSED** unless a line carries another label.

**State of the repository (FACT).** While this section was written, HEAD of `claude/charming-hamilton-faq25e` moved from `8a236eb` (scaffold) to `1b6dcc1` (wire contract revision). Against main `010af1e` both add the session's documents and, under `apps/` and `.railway/`, only the new scaffold `apps/edge-bff/screener/` (`git diff --name-only 010af1e HEAD -- apps .railway`, checked 2026-10-28). Every other `apps/` and `.railway/` citation below holds at main and at HEAD. The scaffold's `src/core/contract.ts` is work in progress, so it is cited with the commit named (`git show <commit>:apps/edge-bff/screener/src/core/contract.ts`). External prices were read from Railway's documentation on 2026-10-28 and can change; they are re-read at decision time.

Labels and evidence notation as in TARGET ARCHITECTURE. Report sections are cited by name (TARGET ARCHITECTURE §6.x, PAGE LOAD SEQUENCE §6c.x, API CONTRACT §8.x, PERFORMANCE EVIDENCE §11.x, PERFORMANCE BENCHMARK PLAN §11b.x).

### 6d.1 What EDGE is today for several users (FACT)

| Area | State | Evidence |
|---|---|---|
| Identity | One owner, one login, one password verifier: `EDGE_OWNER`, `EDGE_LOGIN`, `EDGE_PASSWORD_VERIFIER` are required settings; sign-in compares the body with the one login; every session row is created for `settings.owner`, and the session check refuses any row whose `owner_key` is not `settings.owner` | `apps/edge-bff/app/config.py:12-14, 47-50`; `apps/edge-bff/app/main.py:414, 422, 247-252` |
| Owner on every route | Routes pass `settings.owner`, never an owner read from the session; the Backtest routes take `owner = self.settings.owner`; Orc receives `X-Saniti-Owner: settings.owner` | `main.py:445-653` (for example 445, 579, 653); `apps/edge-bff/app/backtest.py:1050` |
| Stores already keyed by owner | `edge_bff.sessions`, `jobs`, `conversation_ui`, `backtest_jobs` carry `owner_key`; Orc keeps conversations per owner from the `X-Saniti-Owner` header | `apps/edge-bff/app/store.py:59-65, 78-95, 240-322`; `backtest.py:516-526`; `PROJECT_CONTEXT.md:198` |
| edge-bff process | One uvicorn process, one replica, `sfo`; healthcheck `/ready` (120 s). The README: "Use one uvicorn process/one replica initially … authentication attempt limiting is process-local" | `.railway/railway.ts:181-190`; `apps/edge-bff/Dockerfile:33`; `apps/edge-bff/README.md:323-324` |
| edge-bff database pool | `POOL_MIN 1, POOL_MAX 6` per process, "well under the edge_bff_login limit of 20"; live: `edge_bff_login` `rolconnlimit` = 20, `max_connections` = 500 | `store.py:22-27`; live `pg_roles`, `pg_settings` read 2026-10-28 (read-only) |
| edge-bff in-process state | Sign-in attempt limiter `failures` (per IP, 5 a minute; "this deployment intentionally uses one uvicorn process"); model-list cache 600 s; one HTTP client to terminal-api; the Backtest catalog cache 60 s; the Backtest preview latest-wins maps `previews` and `preview_pages`, keyed by owner | `main.py:54, 167-171, 401-412, 558-574`; `backtest.py:44, 48, 934-936, 1002-1033` |
| edge-bff loops | The Orc job loop and the Backtest job loop claim rows with `FOR UPDATE SKIP LOCKED` under leases, so two processes would share them safely | `store.py:158-169`; `backtest.py:503-526, 528-532` |
| terminal-api | One replica in `sfo`, two uvicorn processes. Every browser and worker request through the gateway key acts as one subscriber (`TERMINAL_PROXY_SUBSCRIBER`, dev subscriber 2); its quotas are overridden to 1,000,000,000, TEMPORARY (decision U1 / [D-U1]). Each `/bundle` takes that subscriber's advisory lock | `.railway/railway.ts:158-161`; `apps/terminal-api/Dockerfile:10`; `apps/terminal-api/app/main.py:148-179, 319-327`; `apps/terminal-api/app/store.py:45-46`; `BACKTEST_END_TO_END.md:268-274`; `apps/edge-bff/backtest/CONTRACT.md:28, 674` |
| Default terminal quotas | `files_per_hour` 60, `tickers_per_hour` 30, `tickers_per_day` 150, `megabytes_per_day` 300 per subscriber | `database/migrations/20261025_100_create_terminal_schema.sql:79-83` |
| Terminal under concurrency | 20 concurrent `/bundle` (packs): median 0.53 s, max 0.71 s (before packs: 1.39 s, 3.39 s). Still open: one terminal account per EDGE user and quota counters, then a 50-100 user load test (proposed, not approved) | `ERRORS_AND_SOLUTIONS.md:2302-2307`; `FUTURE_PLAN.md:882-924` |
| backtest-worker | One replica, `sfo`; two compute threads (jobs, previews); keeps one job in memory (409 `BUSY` while it runs; only the latest job's result is kept); previews one at a time in arrival order. edge-bff's loop dispatches one job at a time and waits on `BUSY` | `.railway/railway.ts:176-180`; `apps/backtest-worker/src/server.ts:10-25, 108-114, 197-235, 269-279`; `backtest.py:611-614, 776-781` |
| backtest-worker measured usage | Railway one-minute peak 1.31 GB (12-stock preview, run and cancel within the minute); 0.32 GB for the cold API sequence; CPU peak 0.43 vCPU. Bucket download from `sfo`: 28.35 MB in 6.1 s (4.7 MB/s); in `sin` the terminal-api calls crossed to `sfo` (`/bundle` median 892 ms against 166 ms), so the worker stays in `sfo` | `apps/backtest-worker/README.md:431, 435-440` |
| Regions | Every service in `sfo`; the `terminal-display` bucket in `sin`; the other buckets in `sjc`; Postgres in `sfo` with a 4 GB memory limit | `.railway/railway.ts:7-13, 21-24` |
| Volumes and replicas | `market-python-sandbox` runs "one replica because of the volume" | `PROJECT_CONTEXT.md:87` |
| Recorded resource cost | Postgres page cache of about 6 GB counted as memory: "about USD 60/month at 6 GB" (Railway usage API) | `RAILWAY_CHANGELOG.md:4222-4225` |
| Container limit seen | `serviceInstanceLimits` 24 GB memory and 24 vCPU (market-python-sandbox, 2026-10-08) | `RAILWAY_CHANGELOG.md:791-793` |
| AI cost per message | Examples USD 0.0004 (greeting) to USD 0.016 (Z-score analysis) per message; one shared OpenRouter key with a USD budget the user raises | `RAILWAY_CHANGELOG.md:1092-1097, 302, 1136` |

**Railway pricing (FACT, Railway documentation, read 2026-10-28).**
- Container usage on Hobby and Pro: RAM USD 10 per GB-month (USD 0.000231 per GB-minute); vCPU USD 20 per vCPU-month (USD 0.000463 per vCPU-minute); network egress USD 0.05 per GB; volume USD 0.15 per GB-month. Hobby USD 5 a month including USD 5 of usage; Pro USD 20 including USD 20. Per service: Hobby 6 replicas, Pro 42 (https://docs.railway.com/reference/pricing/plans).
- "You are only charged for the resources you actually use" (https://docs.railway.com/reference/pricing): memory is billed as resident memory, not as the configured limit.
- Private network: "Internal traffic doesn't count toward egress billing" (https://docs.railway.com/networking/private-networking/how-it-works).
- Buckets: egress "unlimited and free, whether that's using presigned URLs or via the S3 API"; storage USD 0.015 per GB-month (recorded from Railway's bucket billing page on 2026-10-24, `verification/terminal_api/PHASE1_PHASE2.md:271-272`).
- Replicas: in one region Railway "will randomly distribute public traffic to the replicas of that region"; across regions it routes to the nearest region; "Railway does not support sticky sessions"; services scale vertically up to the plan's vCPU and memory limits (https://docs.railway.com/reference/scaling). The page describes no horizontal autoscaling (INFERENCE: the replica count is set by hand).
- Healthchecks run at deploy time only: "Railway does not monitor the healthcheck endpoint after the deployment has gone live"; default timeout 300 s (https://docs.railway.com/reference/healthchecks).

Which plan the project is on is UNKNOWN (M-U1).

**What this means (INFERENCE).** EDGE is a single-owner application with a multi-owner data model: every store is keyed by `owner_key`, but identity, sign-in, the terminal account and several in-process maps assume one owner and one process. The Screener can be built multi-user-ready without waiting for EDGE accounts (6d.3, 6d.8).

### 6d.2 Shared across users: computed once per publication

The Screener's inputs are public market data from one rack publication; only the screen definition differs between users. Everything that depends on the publication alone is computed once per publication (per worker replica) and served to every user.

| Item | Computed | Key | Shared how | Evidence or reason |
|---|---|---|---|---|
| Bars of every ticker (the `price` xsection file) | Once per publication per replica | `price_data` | Every screen reads the same in-memory snapshot; 0 bytes from the bucket per request | TARGET ARCHITECTURE §6.5, §6.7; asserted in PERFORMANCE BENCHMARK PLAN §11b.3 column B |
| 53 indicators at registry defaults (76 outputs), tails of `SCREENER_WITHIN_MAX` + 1 bars | Once per publication per replica: 8.1-10.2 s wall on one thread, about 67 MB | (`price_data`, `screener_engine`) | Every default-parameter condition of every user is a lookup | FACT timing `audit/benchmark.md` §2d; size arithmetic TARGET ARCHITECTURE §6.7 |
| Universe attributes, remarks (P4), default ranks | Once per publication | same | `GET universe` bytes are identical for every user | TARGET ARCHITECTURE §6.7 |
| Every preset's match and near counts | Once per publication | same | Sent inside the catalog to every user | TARGET ARCHITECTURE §6.7; PAGE LOAD SEQUENCE §6c.4 |
| Each available preset's full result (PROPOSED pre-warm) | Once per publication | (`price_data`, `screener_engine`, `screener_registry`, `definition_hash`) | A preset click by any user is a cache hit | PAGE LOAD SEQUENCE §6c.4 |
| Catalog and universe JSON bytes and their `ETag` | Once per publication by the worker; held by edge-bff | (`price_data`, `screener_registry`) | Every page open of every user is a `200` from edge-bff memory or a `304` | PAGE LOAD SEQUENCE §6c.5 |
| Result cache (gzip response bytes) | On the first request for a definition | (`price_data`, `screener_engine`, `screener_registry`, `definition_hash`) | Two users with the same screen share one computation | API CONTRACT §8.10 (this section adds `screener_registry`, 6d.12) |
| Counts of saved screens | On request | (`price_data`, `definition_hash`) | Identical definitions of different users are counted once | API CONTRACT §8.6 |
| Series LRU for custom parameters | On request | (`price_data`, `screener_engine`, id, canonical params, output) | RSI(7) computed for one user serves every user's RSI(7) | TARGET ARCHITECTURE §6.7 |

**Why sharing is safe (PROPOSED rule, with its test).** A `run`, `counts` or `preview` answer is a function of the publication, the versions and the definition only: it carries no owner, no saved-item name and no watchlist flag (watch stars come from `GET watchlist`, API CONTRACT §8.7), and `definition_hash` is computed with labels removed (API CONTRACT §8.3). A test asserts that, computed fresh for two owners, the run answers for the same definition are identical apart from `timings_ms` (API CONTRACT §8.5); a cache hit returns the first computation's bytes, timings included. INFERENCE: the one thing a cache hit can reveal is that some user ran the same definition earlier in the publication (a faster answer); no content of another user is exposed.

**Skip the recompute when nothing changed (PROPOSED refinement of TARGET ARCHITECTURE §6.5 rule 5).** A publisher run writes a new `finished_at` even when no session was added (FACT: two runs a day, `apps/terminal-publisher/publisher.py:17-18`; every run ends by writing `state.json` with `finished_at` = now, `publisher.py:549-554`). When the new index names exactly the files the replica already holds (same sha256 set), the replica keeps its snapshot and only advances `published_at`: no download, no 8-10 s recompute, no swap.

### 6d.3 Per user

| Item | Where | Key | Limit |
|---|---|---|---|
| Session and CSRF | `edge_bff.sessions` (existing) | `token_hash` → `owner_key` | Existing (`store.py:59-65`) |
| Saved screens and My metrics | New `edge_bff` table (P12 (a), decided) | `owner_key` | `SCREEN_LIMIT` (PROPOSED ≤ 500, the `PIN_LIMIT` precedent, API CONTRACT §8.9) |
| Watchlist (one) | New `edge_bff` table | `owner_key` | `WATCHLIST_LIMIT` |
| Run and preview in flight | edge-bff memory, latest wins | (`owner_key`, page) | One `run` and one `preview` per page (6d.6) |
| Worker lane | Worker memory, per replica | Owner tag (6d.6) | `SCREENER_OWNER_INFLIGHT` per owner |
| Browser conveniences and the cache pointer | `localStorage` `scr.*`, `scr.boot`; IndexedDB `terminal-files` | Login (a pointer of another login is dropped) | PAGE LOAD SEQUENCE §6c.3 |

Nothing per user is computed by the worker or held in its snapshot. Every per-user row is keyed by the `owner_key` of the session, so when EDGE gains user accounts (6d.8) the Screener's tables, routes and caches need no change: only the owner's source changes from `settings.owner` to the session row (`store.session` already returns `owner_key`, `store.py:63-65`).

### 6d.4 `screener-worker`: replicas, start, publication swap

**A replica is stateless by construction (PROPOSED).** Its whole state is a pure function of (rack publication, `screener_engine`): the snapshot, the pre-warmed results and the caches. Two replicas at the same publication hold the same `snapshot_digest` (TARGET ARCHITECTURE §6.7 Auditability), which the refresh log line records and a test compares. No replica owns a user, a job or a session; any replica can answer any request. This is unlike the backtest worker, which keeps the one job and its result in memory (`server.ts:20-25, 113`), so its replicas would need job-affine routing (6d.8).

**Memory per replica (INFERENCE from FACT components).**

| Component | Size | Label and evidence |
|---|---|---|
| Bars of 845 tickers after load (JSON parse and bar build) | RSS 229 MB after load; peak 279 MB for a load-only process | FACT, `audit/benchmark.md` §2 |
| All 53 defaults computed on top | Peak RSS 299 MB | FACT, `audit/benchmark.md` §2d |
| Decoding all published packs with the core's reader | RSS 190 MB | FACT, `audit/benchmark.md` §4 |
| Inflated `price` document during a refresh | About 75-80 MB, transient | INFERENCE, TARGET ARCHITECTURE §6.5 |
| Default tails kept | About 67 MB | Arithmetic, TARGET ARCHITECTURE §6.7 |
| Each extra compute thread | Its own V8 heap, plus a copy of the bars unless they move to SharedArrayBuffer columns | INFERENCE; TARGET ARCHITECTURE §6.4 (SharedArrayBuffer only after a bit-parity test) |
| Series LRU and result cache | `SCREENER_CACHE_BYTES`, set at the knee of the hit-ratio curve | PERFORMANCE BENCHMARK PLAN §11b.4 |
| Previous snapshot kept during the grace window (below) | About one snapshot again, for minutes twice a day | PROPOSED |

INFERENCE: steady RSS about 0.4-0.7 GB per replica with K = 2 and shared bars; about 0.7-1.2 GB at the peak of a refresh with the previous snapshot alive. This sits inside TARGET ARCHITECTURE §6.4's 0.5-1 GB and below the 2 GB starting limit (§6.17); the limit is then set to the measured S19 peak × 1.5 (§11b.4). For comparison (FACT), the backtest worker peaked at 1.31 GB and idles near 0.32 GB (`apps/backtest-worker/README.md:439-440`).

**Start of a replica (INFERENCE from FACT components).**

| Step | Time | Evidence |
|---|---|---|
| `GET /state`, then `POST /xsection` for the missing files | Below 1 s | `/bundle` median 166 ms from `sfo` (`audit/benchmark.md` §4) |
| Download of about 15-30 MB from the `sin` bucket | About 3-7 s at the 4.7 MB/s measured from `sfo` | FACT rate `apps/backtest-worker/README.md:431` |
| Inflate, sha256 check, decode | About 3 s | FACT 2.77-3.32 s for all packs, `audit/benchmark.md` §4 |
| Cross-check with 845 `/manifest` calls | About 2.3 s (can overlap the decode) | TARGET ARCHITECTURE §6.5 rule 4 |
| 53 defaults | 8.1-10.2 s on one thread; PROPOSED: at start, when no snapshot serves yet, split over the K threads (about 10/K s) | FACT `audit/benchmark.md` §2d |
| Total to `/ready` | About 15-25 s on one thread, about 10-15 s split over K = 2 | INFERENCE; measured as S24 (6d.11) |

**Deploys and new replicas (PROPOSED).**
- The Railway healthcheck path is `/ready` (200 only with a loaded snapshot), with a timeout of at least twice the measured cold start; the default 300 s already covers it. A new deployment then becomes active only with a snapshot, and the old one serves until then (Railway healthchecks, FACT above). TARGET ARCHITECTURE §6.17 names `/health` as the healthcheck; this changes it to `/ready` (6d.12). Liveness after deploy is not monitored by Railway (FACT), so edge-bff's `/health` polling stays the live signal.
- Whether Railway sends traffic to a replica added by raising the replica count before it passes the healthcheck is UNKNOWN (M-U3). Until settled, a replica that is not ready answers 503 `SCREENER_NOT_READY` with `Retry-After`, edge-bff retries once on a new connection (another replica, when the private network spreads connections, M-U2), and the page keeps its cached paint (PAGE LOAD SEQUENCE §6c.6).
- No volume: a Railway volume pins a service to one replica (FACT, `PROJECT_CONTEXT.md:87`). `SCREENER_CACHE_DIR` lives on the container's own disk; a cold replica downloads from the bucket, whose egress is free (FACT above). Whether that disk survives a process restart inside one deployment is UNKNOWN (M-U7); either way the cost is one grant and 15-30 MB per replica start.

**Publication swap across replicas: version skew (PROPOSED).** Each replica polls `/state` every 60 s and refreshes on its own (TARGET ARCHITECTURE §6.5 rule 1), so for up to about 60 s plus one refresh after a publication, replicas serve different `price_data` (INFERENCE). With random distribution and no sticky sessions (FACT above), consecutive requests of one page could alternate between versions. Four rules remove that:
1. **Pinning.** `run` and `counts` gain an optional `data_version` (the `price_data` of the page's catalog), as `preview` already has (`PreviewRequest`, contract.ts line 306 at `1b6dcc1`; `RunRequest` line 233 and `CountsRequest` line 327 have none). A replica answers at the requested version when it holds it.
2. **Grace window.** After a swap a replica keeps the previous snapshot for `SCREENER_PREVIOUS_GRACE_S` (PROPOSED 600 s), so a page pinned to the previous version is served by any replica that already swapped. Memory cost: about one snapshot for ten minutes twice a day (INFERENCE: a few cents a month at the per-minute RAM price).
3. **Ahead of the replica.** A request pinned to a version newer than the replica holds answers 409 `DATA_VERSION_PENDING`; edge-bff retries once on a new connection, then answers 503 `SCREENER_NOT_READY` with `Retry-After: 2`, which the page already handles. A request pinned to a version older than the previous one keeps the existing 409 `DATA_VERSION_CHANGED` (the page re-reads the catalog and re-runs, API CONTRACT §8.6).
4. **Deterministic catalog bytes.** The catalog's `data.refresh` reports the publication's outcome (`ready` or `failed_keeping_previous`), equal on every replica; the transient `refreshing` and the snapshot age stay on `/health` (the scaffold's catalog field `refresh?: RefreshState` admits `refreshing`, contract.ts lines 48 and 57 at `1b6dcc1`). Catalog bytes, and so the `ETag`, are then equal across replicas and edge-bff processes for one publication, and a repeat page open gets its `304` whichever replica built the bytes.

**Threads before replicas (PROPOSED, INFERENCE on cost).** RAM is billed on resident memory and each replica holds its own snapshot, so a second replica roughly doubles the Screener's memory bill while a second thread on shared bars adds one heap. Capacity is therefore raised in this order: K threads (up to the rule of §11b.4: S5 p95 at concurrency K ≤ 1.5 × single, RSS × 1.5 within the limit, Backtest job duration +5% at most), then replicas. A second replica for availability is a separate choice (P32).

**Per-replica caches.** Result cache and series LRU stay in each replica's memory. Every pre-warmed item (defaults, presets, universe, counts) exists on every replica, so the most common answers hit anywhere; only repeated custom screens lose hit ratio by up to a factor R. A shared cache service (for example Redis) is not proposed: it would add a service and a network hop to save CPU that costs about USD 0.0000039 per uncached custom screen (6d.9). It is reconsidered only if S22 shows custom-screen repeats across replicas dominating CPU (P34).

### 6d.5 edge-bff: relaying bytes, and more than one process or replica

**Relay as gzip bytes (PROPOSED).** FACT: the Backtest relay decodes the worker's JSON into Python and encodes it again (`backtest.py:949-968`; the catalog route returns `JSONResponse(self.catalog['data'])`, `backtest.py:1067`), on the single uvicorn process. The first scaffold declared that the worker answers `run`, `preview` and `counts` gzip-encoded when asked (`WORKER_RESPONSE_ENCODING = 'gzip'`, contract.ts line 444 at `8a236eb`); the revision `1b6dcc1` no longer declares it, so the encoding between worker and edge-bff is open in the code (FACT). This section proposes keeping gzip. edge-bff then:
- reads at most `SCREENER_MAX_RESPONSE_BYTES` of compressed bytes, checks status and content type, and passes the bytes to the browser with `Content-Encoding: gzip`, the worker's `ETag` and the house `no-store`; it never parses a 2xx body;
- parses only error bodies (small) to map codes as `ask()` does;
- decompresses only for a client that sends no `Accept-Encoding: gzip` (INFERENCE: no current browser).

Effect (INFERENCE): no JSON work on edge-bff's event loop per answer, and egress counted on compressed bytes (37 KB instead of 112 KB for 845 × 5 values, FACT, PERFORMANCE EVIDENCE §11.5). Catalog and universe are held as gzip bytes too.

**In-process state with more than one process or replica.**

| State | Safe with N > 1? | Proposal | Evidence |
|---|---|---|---|
| Sign-in attempt limiter | No: the limit becomes 5 × N per IP per minute | Move to Postgres before N > 1 (EDGE-wide, 6d.8) | `main.py:401-412`; `apps/edge-bff/README.md:323-324` |
| Model-list cache, terminal-api client, `ready` flags | Yes: caches and handles only | Keep | `main.py:54, 167, 171, 558-574` |
| Backtest catalog cache (60 s) | Yes: each process may lag up to 60 s | Keep | `backtest.py:44, 934, 1056-1070` |
| Backtest preview latest-wins (`previews`, `preview_pages`) | Partly: order holds within one process only; the page's own abort still cancels the older fetch, so a superseded preview may still be computed (cost, not correctness) | Keep | `backtest.py:935-936, 1002-1033` (ERRORS M247 context) |
| Orc and Backtest job loops | Yes: leases with `SKIP LOCKED` | Keep; the backtest worker's single job slot still serialises jobs (6d.8) | `store.py:158-169`; `backtest.py:516-526, 776-781` |
| Screener catalog and universe cache | Yes, with two rules: replace only by a later `published_at` (never move back when `/health` reaches a replica that has not swapped), and use the worker's `ETag` | Monotonic cache; plus the drop on a newer worker answer (PAGE LOAD SEQUENCE §6c.5 item 4) | API CONTRACT §8.4 |
| Screener latest-wins | Partly, as the Backtest preview | Keyed by (`owner_key`, page) instead of owner alone (6d.6); fairness enforced in the worker, which every process reaches | API CONTRACT §8.9 |
| Database pool | N × `POOL_MAX` 6 must stay ≤ `rolconnlimit` 20 of `edge_bff_login`: at most 3 processes or replicas | Before N > 3: raise the role's limit by migration or lower `POOL_MAX` | `store.py:22-27`; live `pg_roles` |

**When edge-bff needs more than one process (INFERENCE).** At today's load the session check costs about 4 ms over a static file (`/api/v1/auth/session` median 221 ms against 217 ms from the sandbox, FACT `RAILWAY_CHANGELOG.md:4917-4918`), and a Screener answer becomes a byte relay. edge-bff's limit is the event loop and the thread pool of `asyncio.to_thread` calls, measured as S25 (6d.11). The first step, if needed, is `--workers 2` in the same container (the same statelessness fixes as replicas; the pool rule allows it); replicas follow on the same rules. Moving edge-bff (or the worker) to a region nearer Indonesia is not proposed: Postgres and terminal-api are in `sfo`, and the backtest worker measured that a service in `sin` pays every call to `sfo` (FACT, `apps/backtest-worker/README.md:435-438`). It is revisited only with timings from the user's location (06c L-U4).

### 6d.6 Concurrency limits and fairness

| Layer | Rule (PROPOSED) | Why |
|---|---|---|
| Page | One `run` in flight; edits debounced 350 ms; the previous fetch aborted (PAGE LOAD SEQUENCE §6c.4 S8) | A typing user sends one computation, not one per keystroke |
| edge-bff | Latest wins per (`owner_key`, page): one `run` and one `preview` per page, via `client_order {page, seq}`. Not per owner alone | Two tabs, or several people sharing today's single login, must not cancel each other's screens. FACT: the Backtest's per-owner map lets a preview from one page replace another page's preview (`backtest.py:1022-1026`) |
| edge-bff → worker | An opaque owner tag `x-screener-owner` = the first 16 hex of HMAC-SHA256(`SCREENER_WORKER_KEY`, `owner_key`) on every call | The worker can be fair per owner without learning the owner's key |
| Worker admission | Cache hits (result cache, pre-warmed items, counts) are answered at once, outside every queue and budget | They cost nothing |
| Worker per-request budget | Refused before compute when the cost model exceeds `SCREENER_MAX_CPU_MS` (existing 422 `LIMIT_EXCEEDED {limit:"compute_budget", costliest}`) | One request cannot hold a thread past the budget (API CONTRACT §8.8-8.9) |
| Worker per-owner lane | At most `SCREENER_OWNER_INFLIGHT` (PROPOSED 2) running per owner tag per replica; further requests of that owner wait in the owner's lane, where a newer request of the same page replaces a waiting one | A heavy user slows only themself |
| Worker scheduling | Round-robin across owner lanes (deficit round robin weighted by the cost model), K threads | Light users keep their latency while a heavy user loops |
| Worker queue | `SCREENER_QUEUE` total waiting (2 × K, §11b.4), then 409 `BUSY` | Bounded memory and wait |
| Deadline | `SCREENER_DEADLINE_MS` → 504 `TIMEOUT` | Existing |

Per-owner rate limits (CPU seconds per minute per owner, or tiers) are not part of the design until the user decides who the users are (P29, P33). Enforced per replica, any per-owner bound becomes at most R times the bound across R replicas (INFERENCE); a strict global bound would need shared state (a Postgres counter written by edge-bff from each answer's `timings_ms`), which is proposed only if P33 asks for strict quotas.

`DATA_VERSION_PENDING` never reaches the page: edge-bff turns it into the existing `SCREENER_NOT_READY`, which already has its message. A per-owner limit, if P33 adds one, gets its rule in the catalog's `limits[]`, how to pass it, one right and one wrong example, and a message that names the problem and the fix, as API CONTRACT §8.8 does for the existing refusals (AGENTS.md "Gates and evidence").

### 6d.7 terminal-api account and quotas under many users

**The Screener's terminal-api traffic does not grow with users (INFERENCE from the design).** Per replica and per publication: one `/state` poll a minute (no quota, no audit, FACT `apps/terminal-api/app/main.py:297-305`), one `POST /xsection` for 2-4 files (one audit row under `REF`), 15-30 MB from the bucket (free egress), and 845 `/manifest` calls (no quota; terminal-api keeps manifests in memory until the next publication, FACT `apps/backtest-worker/README.md:262-266`). Pages never call terminal-api for the Screener (the preview's bars come from the worker, TARGET ARCHITECTURE §6.18 C2).

| R replicas | Grants per day (2 publications, no restart) | Bytes per day | Default quota per subscriber |
|---|---|---|---|
| 1 | 2 | 30-60 MB | `files_per_hour` 60, `megabytes_per_day` 300 |
| 3 | 6 | 90-180 MB | same |
| 5 | 10 | 150-300 MB | same |

With the 6d.2 "skip when unchanged" rule, a run that publishes the same files grants nothing. FACT: all Screener grants share the one gateway subscriber with every browser and the backtest worker, under the TEMPORARY 1e9 override (6d.1). INFERENCE: without the override, R ≥ 5 alone would reach `megabytes_per_day` 300, and the browsers' Terminal and Backtest traffic would come on top. When U1 is replaced, the Screener needs its own service identity with its own quota row, apart from the people's accounts (P31). The Screener does not depend on the override at R ≤ 3 on its own (INFERENCE from the table).

### 6d.8 What multi-user EDGE still needs outside the Screener (separate EDGE-wide decision)

These are not Screener work, but "many users" is not possible without them. Each is FACT about today, with the change it needs (PROPOSED as a list, not designed here).

The labels E1-E6 in the next table are local to this section; they are not the `FUTURE_PLAN.md` proposals E1-E5.

| # | Need | Today (FACT) | Change |
|---|---|---|---|
| E1 | User accounts | One owner, one login, one verifier (`config.py:12-14, 47-50`; `main.py:250, 414`) | A user directory in `edge_bff` (login, password verifier, `owner_key`, status, role), invitation and disabling, password reset; routes take the owner from the session row instead of `settings.owner` |
| E2 | Sign-in limiting | Per process, per IP (`main.py:401-412`) | Per login and per IP in Postgres |
| E3 | Terminal identity and quotas | One gateway subscriber for everyone, 1e9 override TEMPORARY, one advisory lock serialising every user's `/bundle` | The proposal already on record: one terminal account per EDGE user, quota counters instead of log aggregates, then a 50-100 user load test (`FUTURE_PLAN.md:902-924`; `ERRORS_AND_SOLUTIONS.md:2307`), plus a service identity for the workers (6d.7) |
| E4 | AI cost per user | One OpenRouter key and budget for all messages; about USD 0.0004-0.016 per message (`RAILWAY_CHANGELOG.md:1092-1097`) | Per-user AI budgets and their refusal message. INFERENCE: this, not the Screener, is the largest marginal cost of an EDGE user |
| E5 | Backtest throughput | One job at a time for the whole EDGE (`server.ts:20-25, 113, 269-279`; `backtest.py:611-614`); the claim already rotates across owners (`backtest.py:516-526`) | Several job slots or worker replicas with job-affine result fetches; a separate design |
| E6 | Data terms | — | Whether each source (IDX prices, broker summary data, events) may be shown to several users is UNKNOWN (M-U6) |

The Screener is built so that E1 changes only where the owner comes from (6d.3).

### 6d.9 Cost model

**Formula (INFERENCE; units in brackets).**

```
monthly_usd = 10    × Σ_replicas RSS_avg [GB]                       (RAM)
            + 20/2,592,000 × CPU_s_month [vCPU·s]                    (CPU; 30 days = 2,592,000 s)
            + 0.05  × egress_month [GB]                              (edge-bff → browsers; private network and bucket egress free)
            + 0.015 × bucket_storage [GB]                            (xsection files)

CPU_s_month = R × P × c_refresh  +  Q × c_run  +  idle
Q           = N × runs_per_user_day × (1 − h) × trading_days
R           = max(R_availability, ceil(U × r × (1 − h) × c_run / (K × u)))
```

| Symbol | Meaning | Value used below | Source |
|---|---|---|---|
| `RSS_avg` | Resident memory per replica | 0.6 GB (K = 2), 0.8 GB (K = 4) | INFERENCE, 6d.4 |
| `P` | Publications per month | ≤ 62 (two runs a day) | `apps/terminal-publisher/publisher.py:17-18`; fewer with the 6d.2 skip |
| `c_refresh` | CPU per refresh | 15-20 vCPU·s | INFERENCE from FACT: defaults 9.6-10.7 s CPU, decode 2.9-3.4 s, parse 0.6 s (`audit/benchmark.md` §2, §2d, §4) |
| `c_run` | CPU per uncached screen | 0.5 vCPU·s (three custom conditions; default-only screens are lookups) | FACT range 0.35-0.56 s wall, 565 ms CPU, `audit/benchmark.md` §2a-c |
| `N` | Users who use the Screener on a trading day | Scenario | UNKNOWN (M-U5) |
| `runs_per_user_day` | Debounced runs per user per day | 200 | INFERENCE (about 20 minutes of editing) |
| `h` | Share of runs served from a cache | 0.5 | INFERENCE; measured (S13, S22) |
| `U` | Users editing at the same moment | 0.3 × N | INFERENCE (M-U5) |
| `r` | Uncached-run rate of an editing user | 0.15 per s | INFERENCE |
| `u` | Target thread utilisation | 0.7 | PROPOSED |
| egress | Bytes to browsers | About 100 MB per user-month (10 opens a day, mostly `304`; 200 runs of about 20 KB gzip) | INFERENCE from PERFORMANCE EVIDENCE §11.5 (37 KB gzip for 845 × 5 values) |
| `bucket_storage` | xsection files kept | Below 0.1 GB (two indexes kept, TARGET ARCHITECTURE §6.5) | INFERENCE |

**Capacity of one replica (INFERENCE).** K × u / (r × (1 − h) × c_run) = 2 × 0.7 / (0.15 × 0.5 × 0.5) ≈ 37 editing users at K = 2, about 75 at K = 4.

**Worked cases (INFERENCE; every input above is replaced by Phase 17 and real usage).**

| Case | N daily users (U at once) | R × K | RAM USD/month | Uncached runs/month | CPU USD/month | Egress | Total USD/month |
|---|---|---|---|---|---|---|---|
| Dev today | 1 (1) | 1 × 2, 0.5 GB | 5.00 | 2,200 | 0.01 | 0.1 GB, 0.01 | ≈ 5 |
| Team | 30 (9) | 1 × 2 | 6.00 | 66,000 | 0.25 | 3 GB, 0.15 | ≈ 6.4 (≈ 12.4 with a second replica for availability) |
| Many | 150 (45) | 2 × 2 | 12.00 | 330,000 | 1.27 | 15 GB, 0.75 | ≈ 14 |
| Large | 1,000 (300) | 5 × 4 | 40.00 | 2,200,000 | 8.49 | 100 GB, 5.00 | ≈ 53.5 |

Refresh CPU adds about USD 0.01 per replica a month (R × 62 × 20 s × USD 20 / 2,592,000 s). Postgres adds no market-data load at request time: each request costs one session `SELECT` through the existing pool (`store.py:63-65`), plus saved-item and watchlist statements keyed by `owner_key`; the publisher adds one bounded scan of about 2 s per publication, independent of users (TARGET ARCHITECTURE §6.5). Plan fees (Hobby USD 5, Pro USD 20, each including that much usage) are shared with the rest of the project and not counted here.

**What drives the bill (INFERENCE).** Resident memory per replica: one replica costs about USD 5-8 a month idle or busy, while one uncached custom screen costs about USD 0.0000039 of CPU (0.5 s × USD 20 / 2,592,000 s). Hence: one copy of the bars per replica (SharedArrayBuffer columns, TARGET ARCHITECTURE §6.4), threads before replicas, replicas only on measured triggers, and no Redis or volume. For comparison, one AI message costs USD 0.0004-0.016 (FACT, 6d.1), about as much as one user's whole month of Screener compute in the "Many" case (USD 1.27 / 150 users ≈ USD 0.008, INFERENCE).

### 6d.10 Scaling triggers (PROPOSED thresholds; Phase 17 confirms them)

Signals come from the worker's `run` and `refresh` log lines (TARGET ARCHITECTURE §6.16), extended with `owner_tag` and `replica`, and from Railway's metrics.

| Signal | Threshold | Action | Order |
|---|---|---|---|
| Worker `queue_ms` p95 over 15 minutes in market hours | > 300 ms | Raise K if the §11b.4 rule still holds; otherwise add a replica | 1 |
| 409 `BUSY` share of runs, one trading day | > 1% | Same | 1 |
| Replica CPU, 15-minute average | > 70% of K vCPU | Same | 1 |
| S5-class run p95 through edge-bff | > 2 s (the §11b.5 target) | Same, after checking the log for one owner's lane | 1 |
| Peak RSS during a refresh with the grace snapshot alive | > 70% of the memory limit | Raise the limit to peak × 1.5 | 2 |
| Light owners' p95 while one owner loops heavy screens (S23) | > 1.5 × their solo p95 | Lower `SCREENER_OWNER_INFLIGHT` or the per-request budget | 3 |
| Replica CPU < 20% of K and `queue_ms` p95 < 50 ms for 5 trading days | — | Remove a replica, never below the availability floor (P32) | 4 |
| edge-bff event-loop lag p95 | > 50 ms, or pool waits > 0 at peak | `--workers 2`, then replicas, within the pool rule (6d.5) | 5 |
| `megabytes_per_day` used by the gateway subscriber | > 50% of the quota once the override ends | Service identity for the worker (P31) | 6 |

### 6d.11 What Phase 17 measures to set these (additions to PERFORMANCE BENCHMARK PLAN §11b.3)

| # | Scenario | Measures | Sets |
|---|---|---|---|
| S21 | Multi-owner load: the worker driven directly with 1, 10, 50 synthetic owner tags (from a temporary job service on the private network, the precedent of `feature-05-06-job`, `RAILWAY_CHANGELOG.md:4249`), and edge-bff driven with 10-50 sessions of the one dev owner on distinct pages | `c_run` per class, p50/p95 per owner, `BUSY` share, CPU | `c_run`, K, `SCREENER_QUEUE` |
| S22 | Two replicas at a real publication | Swap time per replica, skew window, `DATA_VERSION_PENDING` and `DATA_VERSION_CHANGED` counts, equal `snapshot_digest`, cache hit ratio per class (preset, empty screen, custom) per replica | Grace window, P34 |
| S23 | Fairness: one owner tag looping S10 (the worst allowed screen), ten tags sending S1 and S5 | Light owners' p95 against their solo p95 | `SCREENER_OWNER_INFLIGHT`, per-request budget |
| S24 | Cold start of a replica, and a replica added by raising the count | Time to `/ready` per step; RSS curve; download rate from `sin`; 503 answers during warm-up | Healthcheck timeout, scale-out lead time, M-U3 |
| S25 | edge-bff relay at 50, 100, 200 concurrent cached answers | Relay overhead p95 against the worker alone, event-loop lag, pool waits | edge-bff trigger |
| — | Private network spread: DNS answers for `screener-worker.railway.internal` from edge-bff with R = 2, and each replica's share of requests in the logs | M-U2 | Retry rule of 6d.4 |
| — | Usage calibration: Railway usage per service (memory GB average, vCPU average) over five trading days, as read for Postgres on 2026-10-22; egress bytes per page open from the page timing script (PAGE LOAD SEQUENCE §6c.9) | `RSS_avg`, egress per user | The cost model's inputs |

Results go to `verification/screener/BENCHMARK.md` with deployment IDs and log locations, as §11b.2 requires.

### 6d.12 Consequences for other sections (PROPOSED; agent A owns those files)

- API CONTRACT §8.3: the catalog's `data.refresh` is the publication's outcome (`ready` | `failed_keeping_previous`); `refreshing` and the snapshot age only on `/health` (6d.4 rule 4).
- API CONTRACT §8.5, §8.6: optional `data_version` on `run` and `counts`; worker 409 `DATA_VERSION_PENDING`, retried once by edge-bff, then 503 `SCREENER_NOT_READY` with `Retry-After: 2` (6d.4).
- API CONTRACT §8.9: "in flight per owner: 1 screen, 1 preview" becomes per (owner, page); new worker limit `SCREENER_OWNER_INFLIGHT`; new variable `SCREENER_PREVIOUS_GRACE_S` (6d.6, 6d.4).
- API CONTRACT §8.10: the result cache key adds `screener_registry`; caches are per replica; catalog and universe held as gzip bytes, replaced only by a later `published_at`.
- API CONTRACT §8.11: header `x-screener-owner` (opaque tag) on every worker call except `/health` and `/ready`; the worker answers `run`, `preview` and `counts` gzip-encoded and edge-bff relays the bytes (6d.5). The scaffold's contract should declare this again: `8a236eb` did, the revision `1b6dcc1` dropped it.
- TARGET ARCHITECTURE §6.5 rule 5: keep the snapshot when the new index names the same files (6d.2); §6.17: healthcheck `/ready` with a timeout of at least twice the measured cold start, no volume, `SCREENER_CACHE_DIR` on the container's disk, start at one replica with the availability floor of P32.
- PERFORMANCE BENCHMARK PLAN §11b.3, §11b.4: S21-S25 and the rows of 6d.11; the trigger table of 6d.10 as the rule for R.
- TEST PLAN: fresh run answers for one definition are identical for two owners apart from `timings_ms`; latest wins per (owner, page); the catalog cache in edge-bff never moves back; version pinning and the grace window; the owner lanes' round-robin.

### 6d.13 Unknowns (UNKNOWN, with the check that settles each)

| # | Unknown | Check |
|---|---|---|
| M-U1 | Which Railway plan the project is on, and its per-replica limits | Railway dashboard, workspace plan; `serviceInstanceLimits` of a service |
| M-U2 | How the private network spreads requests over replicas | DNS answers and per-replica request shares (6d.11) |
| M-U3 | Whether a replica added by raising the count receives traffic before its healthcheck passes | S24 |
| M-U4 | Real RSS per replica, `c_run`, cold start | Phase 17 S14, S18, S19, S21, S24 |
| M-U5 | How many people will use EDGE, how many at once, and how they use the Screener (`N`, `U`, `r`, `h`) | The user's expected numbers (P29); page and worker logs after launch |
| M-U6 | Whether each data source may be shown to several users | The user confirms the terms per source |
| M-U7 | Whether the container disk cache survives a process restart inside one deployment | Restart test; the refresh log's `cached` field |
| M-U8 | Sizes of the catalog and universe answers (06c L-U3) | First dev build |
| M-U9 | Current Railway usage of the EDGE services, the cost baseline | Railway usage API per service, as read for Postgres (`RAILWAY_CHANGELOG.md:4222-4225`) |

### Decisions for the user

Provisional ids, continuing PAGE LOAD SEQUENCE's P24-P28; agent A assigns the final numbers.

- **P29: Who the "many users" are.** (a) A small trusted team; (b) external users or subscribers; (c) both, in stages. This sets the identity work (E1), quotas (P31, P33), AI budgets (E4) and the data-terms check (M-U6). The Screener's design is the same for all three. Recommendation: state the expected number of daily users and users at once, so the triggers and the cost table can be set from them.
- **P30: EDGE user accounts (EDGE-wide, not Screener work).** (a) A user directory in `edge_bff` with invitation-only accounts, per-user `owner_key` and sign-in limits in Postgres (E1, E2); (b) an external identity provider; (c) keep one owner for Screener Phase 1. Recommendation: (c) now, because the Screener is owner-keyed and needs no change later; (a) as its own EXEC item before a second person uses EDGE.
- **P31: terminal-api identity per user and for the workers (EDGE-wide; replaces the TEMPORARY U1 override).** (a) One terminal account per EDGE user plus one service account for `backtest-worker` and `screener-worker` with its own quotas (`FUTURE_PLAN.md:907-924`, items a, b and 4); (b) keep the one account with the override. Recommendation: (a) together with P30 (a); the Screener alone stays within default quotas up to three replicas (6d.7).
- **P32: Availability floor of `screener-worker`.** (a) One replica: a crash leaves 15-25 s of 503 `SCREENER_NOT_READY` while it reloads (deploys stay seamless through the `/ready` healthcheck); (b) two replicas from the first day other people use it, about USD 6 a month more (6d.9). Recommendation: (a) on dev in Phase 1, (b) from multi-user production.
- **P33: Per-user compute limits.** (a) Fair sharing only (per-owner lanes, the per-request budget); (b) add a per-user CPU budget per minute, with its message and rule in `limits[]`; (c) tiers per user class. Recommendation: (a) until P29 is answered; (b) if external users come.
- **P34: Shared result cache across replicas.** (a) Per-replica caches; (b) a shared cache service. Recommendation: (a); revisit only if S22 shows repeated custom screens across replicas dominating CPU (6d.4).


## FLOW INDICATOR PROPOSALS (PHASE 2)

**Request (FACT, user 2026-10-28, `EXEC.md` EXEC-SCREENER and the moved PLAN SCREENER history):** "Fase 2 — Flow/bandarmologi ...
butuh keputusan Anda soal papan transaksi (Regular saja atau semua papan) dan definisi “bandar”. --> semua papan. But also
research kira2 indikator apa yang bisa dipakai untuk screen. MIsal HHI, Buy intensity, propose ke saya 10-20 indicators
nanti." P8 is DECIDED: all boards (Regular, Nego and Tunai combined) is the default for flow metrics. EXEC-SCREENER also
says Phase 2 ships "flow dari indikator yang dipilih user", and that P9, P10 and P20 are decided after this proposal.

**Status.** A proposal for the user to choose from. Nothing was changed in the repository, the database or Railway. Every
indicator, formula, default, threshold and ranking below is **PROPOSED** unless a line carries another label. No threshold
here is validated against returns.

**How it was made.**
- Repository read at `main` `88d3344` (read-only): `apps/edge-bff/backtest/src/core/flow.ts`,
  `apps/edge-bff/terminal/src/data/brokerAgg.ts`, `apps/terminal-publisher/publisher.py`, `verification/terminal_api/DESIGN.md`,
  `DATABASE_SCHEMA.md`, `DATABASE_CATALOG.md`, `UPDATE_TABLE.md`, `ERRORS_AND_SOLUTIONS.md`.
- Live PostgreSQL through pgweb (read-only, statement timeout 30 s), 2026-10-28 02:59-03:20 UTC. Queries ran one at a time,
  each bounded by literal dates; no full scan of `IDX_Broker_Summary`, Feature 02 or Feature 05.
- Inputs: `audit/flow.md`, `audit/verify_flow.json`, APPENDIX B, TARGET ARCHITECTURE §6.11, UNKNOWNS P8, P9, P20.
- Evidence: `evidence/flow_proposals/<file>` (every SQL and its output; the synthetic worker benchmark in
  `evidence/flow_proposals/bench_js/`). Labels FACT, INFERENCE, PROPOSED, UNKNOWN as in the header.
- Verified adversarially on 2026-10-28, 13:55-14:20 UTC (the cited files are unchanged at `8a236eb`). Corrections are
  marked "corrected" in place, and 16.14 lists what was checked, what changed and what stays uncertain
  (`evidence/flow_proposals/verify_*`).

**Live state at read time (FACT).**
- `IDX_Broker_Summary`, F05, F03 and F06 all end on 2026-10-27 (`q03_state_calendar.txt`). A Daily price exists on 2026-10-27
  for the 828 universe stocks of the broker queries (`q13_f05_broker20_result.txt`). Broker lag M243: 0 sessions.
- The newest `Monitoring_Stockbit_Update` row by `started_at` is `51a399f1`, SUCCESS, 14:28-14:53 UTC 2026-10-27. The stale
  RUNNING row `e3331473` is still open (ERRORS D25) (`q04_monitoring.txt`). No round was running during the reads.
- Universe: 844 stocks. 832 traded on some board on 2026-10-27; 828 traded on Regular (`q05_universe.txt`). All-board
  distributions below use the 832; metrics that need a close use the 828 with a price row.

---

### 16.1 Summary

1. **FACT: the proposed set has 20 indicators.**
   - Foreign investor flow: FL01-FL05.
   - Broker ranking, the "bandar" family: FL06-FL09.
   - Concentration and breadth: FL10-FL12.
   - Cost basis and persistence: FL13-FL15.
   - Activity and crossing: FL16-FL18.
   - Broker class: FL19. Insider and major holders: FL20.
2. **PROPOSED first set, 11 indicators:** FL01, FL02, FL04, FL06, FL07, FL08, FL09, FL10, FL12, FL16 and FL18.
   - Three of them (FL07, FL08, FL09) come out of one ranking pass.
   - FL18 is the extra one. It shows how much of an all-board value comes from Nego and Tunai crossings.
   - The other 9 are later options. 9 candidates are rejected with reasons (16.4, 16.8).
3. **FACT: "all boards" is exact only in one way.** The additive components (IDR values, lots, trade counts, nets) are summed
   across boards and sessions. Every ratio, share, ranking, HHI, streak, day count, VWAP, z-score and percentile is then
   computed again from those sums.
   - The catalog encodes this. `foreign_net_1d` allows SUM; `foreign_net_20d` and `foreign_net_turnover_ratio_20d` do not
     (`q02_catalog_f06_f02.txt`).
   - Method check, FACT: for the 38 stocks with no Nego or Tunai row in 280 sessions, the all-board z-score built from the summed
     one-day values equals the stored Feature 06 Regular z-score on all 38 (`q16_f03_zscore280_result.txt`).
4. **FACT, measured: all boards distorts two price-like metrics.** Nego trades are priced and sized away from the market.
   - Top-buyer VWAP distance (FL13): 31 of 828 stocks differ by more than 5 points between all boards and Regular. BYAN:
     +275.8 % on all boards, −5.3 % on Regular (`verify_v05_fl13_regular.txt`). (corrected: `q19` ranked the top buyers
     on all-board nets and took only their Regular VWAP, which gives 34 and −5.0 %; Regular end to end gives 31.)
   - Average trade size (FL17): the 20-session maximum is Rp 2,869 M on all boards and Rp 55.8 M on Regular
     (`q12_f06_window25_result.txt`).
   - PROPOSED (decision D7): these two default to Regular, labelled; every other indicator uses all boards.
5. **FACT: two identities decide what is worth screening.**
   - Foreign net + domestic net = 0 on 1,004 of 1,004 (ticker, board) rows on 2026-10-27 (`q11_f03_vs_f06_latest.txt`;
     ERRORS M154 from 2021). A "foreign vs domestic divergence" therefore carries no information and is rejected.
   - The sum of all broker nets of a stock-day is 0. So the bandar balance (FL09) equals minus the net of every broker outside
     the top-N buyers and top-N sellers. A positive balance means "the rest of the market sold to the top buyers". This is the
     bandarmology premise in measurable form.
6. **FACT: several bandar metrics depend on liquidity; breadth does not** (`q20_liquidity_dependence.txt`).
   - Median buy intensity: 24.3 % in the least liquid third, 12.5 % in the most liquid third.
   - Median |bandar balance|: 4.43 against 2.10.
   - Median net-buy HHI: 0.259 against 0.204.
   - Broker breadth (FL12) has a median of 0.49-0.51 in every third.
   - Fixed thresholds therefore flag illiquid stocks more often; pair them with the ADV floor (decision D10).
7. **FACT/INFERENCE: cost.** Every indicator can be computed in the screener worker from published files, so no new stored
   feature is needed.
   - FL03 and FL06-FL17 come from the planned F05 `broker_window`, with two added columns, `buy_freq` and `sell_freq`.
   - FL01, FL02, FL04, FL05, FL18 and FL19 come from a long all-board series read from Feature 03. (corrected: FL03 was
     listed here; Feature 03 holds no foreign gross buy or sell, so FL03 needs `broker_window` or the F06 one-day columns.)
   - FL20 comes from the insider rows of the events data.
   - Per-date reads, cold: F03 12-26 ms (41-48 blocks, 5 dates), F06 524 ms (1,439 blocks), F05 1.7-1.8 s (1,713-1,769
     blocks, 2 dates) (`q24_f03_per_date_cold.txt`, `verify_v06_f03_per_date.txt`, `q18_per_date_reads_cold.txt`,
     `verify_v07_f05_per_date.txt`). (corrected: F03 was given as 12 ms from one date.)
   - Worker CPU for the whole broker grid: about 0.25-0.29 s on one core (synthetic, `bench_js/worker_cost.txt`).
   - The publisher login can read F05 and `IDX_Broker_Profile` today. It cannot read F03 or F06 (`q25_publisher_grants.txt`).
8. **PROPOSED, P9:** "Bandar" = FL09, the top-3 bandar balance over 10 sessions, all boards, in % of traded value.
   - States Big Acc / Acc / Neutral / Dist / Big Dist at ±10 / ±6, as editable per-condition defaults.
   - FACT, 2026-10-27, 832 stocks: 66 / 70 / 607 / 52 / 37 (`q22_bandar_state_counts.txt`).
   - "Bandar average price" = FL13. The Terminal's Bandar detector should share the same definition.

---

### 16.2 What the stored data gives

**Per (ticker, date, broker, investor type, board): Feature 05 = `IDX_Broker_Summary`, one row per source row (FACT).**
- Columns (`q06_types.sql`, APPENDIX B §B.3): `buy_value`, `sell_value`, `net_value` (IDR, numeric); `buy_lots`, `sell_lots`,
  `net_lots` (lots of 100 shares); `buy_freq`, `sell_freq` (bigint, trade counts); `source_balance_gap`.
- On 2026-10-27 (`q27_f05_latest_shape.txt`):

  | Board | Rows | Tickers | Brokers | Buy value |
  |---|---|---|---|---|
  | Regular | 24,503 | 865 | 89 | Rp 16.350 T |
  | Nego | 338 | 130 | 50 | Rp 1.559 T, 8.7 % of the all-board Rp 17.909 T |
  | Tunai | 19 | 9 | 7 | Rp 0.000 T |

  - No row has buy and sell both zero, so a missing row means no activity.
  - No row has a null frequency or a gap flag.
- Average price = value / (lots × 100). This equals Stockbit "Avg Buy" (verified on 574 rows, `audit/verify_flow.json` C10)
  and the Terminal's `avgPrice` (`apps/edge-bff/terminal/src/data/brokerAgg.ts:25`).
- Frequency (FACT, inference stated): the summed buy frequency equals the summed sell frequency on 1,004 of 1,004
  (ticker, board) rows on 2026-10-27 (`q11_f03_vs_f06_latest.txt`). So the sum is the stock's number of trades. A broker's
  `buy_freq` is the number of trades in which it bought; it does not say who initiated the trade (INFERENCE).

**Per (ticker, date, board): Feature 03 (FACT, `q01_catalog_f03_f05.txt`).**
- Columns: `total_buy_value`, broker counts, `foreign_net_value`, `domestic_net_value`, the class nets (institutional, retail,
  mixed, niche by the current `IDX_Broker_Profile` class), top buyer and seller, top-3 buyer share, `broker_concentration_hhi`
  (|net| HHI).
- A row exists only where that board traded.
- FACT: `foreign_net_value` = F06 `foreign_net_1d` and `total_buy_value` = F06 `foreign_buy_1d + domestic_buy_1d` on 1,004 of
  1,004 rows on 2026-10-27 (`q11`).
- Physically clustered by date (pg_stats 0.897, `audit/flow.md` §1). One date reads 41 blocks cold (`q24`).

**Per (ticker, date, board): Feature 06 (FACT, `q02_catalog_f06_f02.txt`).**
- Columns: foreign and domestic buy, sell and net; trade counts per investor type; stored windows 5-60; ratios; z-scores and
  percentiles; strength; ticket-size metrics.
- Every stored window is per board, on the ticker's sessions. Rows exist only where that board traded.
- Scattered on disk (trade_date correlation 0.047): one date reads 1,439 blocks for 1,446 rows cold (`q18`).

**Per (ticker, board, broker, investor type, date): Feature 02 (FACT).**
- Rolling 5/20/60-session nets, buy days, z-scores, largest buy day.
- Rows are written only where the combination traded that day, so the latest date is sparse. ANTM: 79 of 143 combinations
  present; 20-day foreign net −408.05 B against a true −477.11 B (APPENDIX B §B.3). Not usable for a cross-section.

**Reference and other sources (FACT).**
- `IDX_Broker_Profile`: 112 brokers with `broker_type` and a current-state class (`q21_freq_coverage_sample.txt`):
  - Institutional-heavy 25 (for example AK, BK, CS, DX, KZ, RX);
  - Mixed 23 (CC, LG, MG, NI, OD, SQ);
  - Niche 45;
  - Retail-heavy 19 (DR, EP, GR, KK, PD, XC, XL, YP, YU, ZP).
- `stockbit_insider_transaction` / `idx_event_annotation`: insider (IDX) and ≥ 5 % holder (KSEI) movements (`q26_insider_coverage.txt`).
  - IDX rows: 22,440 since 2019-11-02. KSEI rows: 81,598 since 2017-10-12. Last pull 2026-10-27 14:52 UTC.
  - Since 2026-09-30: 597 IDX rows in 105 tickers and 1,261 KSEI rows in 174 tickers.
  - The publisher can read `idx_event_annotation` and already publishes it as `events/{ticker}/all.json.gz` with
    `shares_change`, price and value (`apps/terminal-publisher/publisher.py:27, 276-286`). It cannot read the raw table.
- Price: close and volume. FACT: price volume equals Regular-board volume (`audit/verify_flow.json` C9). FACT (verification):
  a price bar exists only on days with broker rows, and not on Nego-only days: in the 20 sessions to 2026-10-27, 81
  stock-days of 15 universe stocks have Nego rows and no price bar; no price bar lacks broker rows
  (`verify_v13_calendars.txt`, `verify_v14_nego_only_days.txt`).

**What is not available (FACT unless marked).**
- No order book: no bids, asks, depth or queues.
- No per-trade or tick data. So there is no aggressor side (buyer- vs seller-initiated) and no intraday timing. The order
  imbalance of Chordia, Roll & Subrahmanyam [5] and PIN [6] cannot be computed. "Buy" in the broker summary means the broker's
  clients bought; every trade has a buyer and a seller.
- No client or account identity. A broker's net is the sum over all its clients. YP, for example, is Retail-heavy with
  `broker_type` Foreign; 9 of the 19 Retail-heavy brokers are Foreign-type (`verify_v01_broker_profile.txt`; corrected:
  `q21` shows the class only, not `broker_type`).
- No full shareholder register and no free-float history. Only the insider and ≥ 5 % movements above exist.
- No point-in-time broker class. Feature 03's class columns have `point_in_time_safe = false` (`q01`).
- "Foreign" is the investor type of the source row, never the broker's domicile (catalog, `q01`).
- History caveat (ERRORS M157):
  - From 2016 to August 2020 some brokers (FM, LK) are missing from the source.
  - Foreign + domestic ≠ 0 on about 7 % of Regular rows in that period (verified: 47,296 of 652,016 = 7.25 % in
    2016-2020; 14.7 % in 2016, 3.5 % in 2020; `verify_v15_m157_share.txt`).
  - Broker rankings, concentration and the bandar identity are therefore biased before September 2020.
- Frequency coverage (FACT, `q21`): on sampled dates in 2016, 2020, 2022, 2024, 2025 and 2026, null frequencies occur only on
  tickers that are not 4-letter codes (warrants and rights). Verification: 0 null on 4-letter tickers on 12 more dates
  2017-2026, every board (`verify_v11_freq_coverage.txt`). A sample, not the full history.

---

### 16.3 Computing "all boards" correctly

**Rules (FACT for the arithmetic, PROPOSED as the contract).**

| Quantity | All-board computation | Never |
|---|---|---|
| IDR values, lots, nets, trade counts (F05 rows; F03 `foreign_net_value`, `total_buy_value`, class nets; F06 `*_1d`) | Sum across boards, then across sessions | — |
| Broker rankings, top-N, HHI, breadth | First sum each broker over both investor types and all boards (F02 catalog: "Aggregate both types by broker before counting or ranking brokers"), then rank or count | Ranking per board and adding the results |
| Windows (N-session sums) | Sum the one-day all-board values over the window | Adding stored per-board `*_Nd` columns from the latest rows. A board without a row today has none, though it had flow inside the window: BYAN has only a Regular F06 row on 2026-10-27, stored 20-day foreign net −39.72 B, while the all-board 20-day net is −1,246.00 B (−1,206.28 B on Nego days); 73 universe stocks are affected, 27 by ≥ Rp 1 B (`verify_v09_missing_board_today.txt`, `verify_v10_byan_f06.txt`). (corrected: the CARE example did not show this; CARE has a Nego row today and its stored rows add up: −1.50 + 377.72 = +376.22 B.) |
| Ratios, shares, % of value | Numerator and denominator summed separately, then divided | Averaging or adding per-board ratios |
| Average trade size, VWAP | Σ value / Σ trades and Σ buy value / (Σ buy lots × 100) | Averaging per-board averages |
| Streaks, buy/sell day counts, accumulation days | From the all-board daily value | Adding per-board day counts |
| z-scores, percentiles | Recomputed on the all-board series with the F06 definition (previous 252 values, today excluded) | Reading per-board stored z or percentile as all-board |
| F03 `broker_concentration_hhi`, `top3_buyer_share`, `net_buy_broker_ratio` | Not used for all boards (non-additive; allowed aggregations have no SUM, `q01`); replaced by FL10 and FL12 from all-board broker nets | — |

**Feature_Catalog and DATABASE_CATALOG warnings, and how the proposals meet them (FACT for the text, PROPOSED for the handling).**

| Warning (where) | Handling |
|---|---|
| F05 and F06: "Do not compare across boards or sum across boards." Investor columns: "do not mix boards" (`q01`, `q02`) | The screener never writes an all-board value into a stored feature. It sums only columns whose `allowed_aggregations` include SUM (`foreign_net_1d`, `buy_value`, `net_value`, `buy_freq` ...) and recomputes the rest. Every cell carries `board` ("All boards" or "Regular"). |
| F03 and F02: "Do not combine Regular, Nego and Tunai implicitly; board must remain explicit or be deliberately aggregated" (`q01`, `q02`) | The user's P8 is the deliberate aggregation; `board` stays a parameter on every indicator. |
| `DATABASE_CATALOG.md:32` (Feature 03): "Regular, Nego, and Tunai never mix" | True for the stored table, and it stays true. If an all-board flow feature is ever stored (16.9, option c), its catalog text must say "deliberately aggregated across boards". That goes through `NEW_TABLE_ONBOARDING_PLAN.md`. |
| "Rows are investor-type-specific. Aggregate both types by broker before counting or ranking brokers" (F02) | Every broker metric sums both investor types per broker first. |
| "Do not call this foreign-broker flow or infer broker domicile" (F03 foreign and domestic net) | FL01-FL05 are labelled "foreign investors". Broker domicile is used nowhere. |
| "Aggregate uses current broker reference classification, not point-in-time" (F03 class nets, `point_in_time_safe = false`) | FL19 is a later option. It carries the caveat and is NA for historical evaluation dates (look-ahead). |
| Total buy and total sell are equal by construction; "Never read their difference as net demand" (F03 `total_buy_value`, M154) | The stock-level difference is rejected (R2). Accumulation is measured per broker (FL07-FL15) or per investor type (FL01-FL05). |
| "Do not treat a single high, low ... observation as predictive evidence without historical validation" (all F03 rows) | Thresholds are labelled unvalidated. Validation through the Backtest is a later step (the user: indicators can be added to the Backtest later). |
| F06 z-score: "Overlapping windows make consecutive values dependent"; percentile: "of the ticker's own history, not a cross-sectional rank" | Stated on FL05. Cross-sectional ranks are a separate transform (P7). |
| `source_balance_gap`: "Not a market signal" (F05) | Not used as an indicator. Gap sessions only mark the M157 caveat. |

**Session calendar (FACT / PROPOSED).**
- Stored F06 and F02 windows count the ticker's own sessions.
- The queries here count market sessions: dates that have broker rows market-wide. A ticker without a row on a session
  counts 0 there, and that breaks its streaks.
- The Backtest counts the ticker's price bars (`flow.ts:41-80`). The three calendars differ for suspended tickers and on
  2026-09-17/18, when brokers traded but no price row exists (ERRORS M238; APPENDIX B §B.6; verified: 1 price row on each
  of those dates, `verify_v12_price_0917.txt`). (corrected: they also differ on every stock-day without a trade, which
  market sessions count as 0 and the other two skip, and on Nego-only days, which have broker rows but no price bar: 81
  stock-days of 15 universe stocks in the 20 sessions to 2026-10-27, Rp 794 B of value. The Backtest's `flowData` skips
  broker rows on dates without a price bar (`unmatched_rows`), so its all-board `fnet`, `broker` and `top5` leave that
  flow out; TRUK loses +130.5 B of foreign net (`verify_v13_calendars.txt`, `verify_v14_nego_only_days.txt`).)
- FL05 uses ticker sessions, so that it equals the stored F06 definition (the 38/38 parity above).
- Which one the screener uses is P20 (b), decision D12.

**Where all boards distorts (FACT, measured; decision D7).**
- **Prices:** a Nego crossing can be priced far from the market.
  - Top-3 buyer VWAP distance over 10 sessions, all boards vs Regular: 71 of 828 stocks differ by > 1 point and 31 by > 5 points
    (`verify_v05_fl13_regular.txt`). (corrected: 70 and 34 in `q19`, which ranked the top buyers on all-board nets and
    took only their Regular VWAP.)
  - BYAN +275.84 % vs −5.29 % (Regular end to end; −5.02 % in `q19`); MMIX +58.84 % vs −5.08 %; SKBM +50.36 % vs +6.87 %
    (`q19`, mixed ranking).
  - BAJA −62.19 % vs −9.96 % also has a price-affecting action in its lookback (TARGET ARCHITECTURE §6.12, live L6).
- **Ticket sizes:** average trade size over 20 sessions, all boards vs Regular: p90 Rp 10.34 M vs 7.45 M; maximum Rp 2,869 M
  vs 55.8 M. The 5-vs-20 change has a p90 of +58.7 % vs +38.8 % (`q12`).
- **Counts are not distorted:** the trade-count spike is almost identical on both (p90 1.763 vs 1.785), because Nego trades
  are few (`q12`).
- **Bandar states change little:** between all boards and Regular (top 3, 10 sessions), 37 of 832 stocks change state, none
  flips sign, and 55 change their top net buyer (`q23_board_effect_bandar.txt`).
- **Foreign net, 20 sessions:** 168 of 841 stocks differ and 20 flip sign (`audit/verify_flow.json` C11).
- **Consequence for comparisons:** Stockbit's "Foreign Flow" is Regular only (ERRORS M244), so all-board values differ from
  Stockbit for stocks with Nego foreign flow (CARE). A Regular variant stays available on every indicator.

---

### 16.4 Candidates considered

| Candidate | Verdict | Why (evidence) |
|---|---|---|
| Broker concentration HHI of net buying | **FL10** | User's example; HHI [1][2] on positive broker nets answers "how few brokers hold the net accumulation". Effective number 1/HHI [3] shown with it |
| HHI of gross buy value | Merged into FL11 | Mostly reflects brokers' general market share (median 0.154; liquidity-dependent 0.182 vs 0.108, `q20`) |
| HHI of gross sell value, gap buy − sell | **FL11** | Same stock-period on both sides, so liquidity partly cancels; correlates with FL09 (0.22-0.53, `q20`) |
| HHI of \|net\| (F03 stored) | Rejected as default (R6) | Mixes buyers and sellers; stored 1-day per board, not additive |
| Top-N buyer share of total buy value | Merged into FL08 | FL08 is its net form: the gross form counts brokers that also sold |
| Buy intensity | **FL08** | User's example: top-N net buyers' net / traded value |
| Top-N net accumulation over D (generalised `top5Accumulation`) | **FL07** (Rp) and **FL09** (% of value) | Prototype `topacc` and `bandar`; Backtest `top5` at N = 5 (`flow.ts:108-119`) |
| Broker breadth | **FL12** | Liquidity-neutral (`q20`); the LSV fraction of buyers [4] |
| Foreign net value, D sessions | **FL01** | Prototype `fnet`; Backtest `fnet` |
| Foreign net as % of traded value | **FL02** | Prototype `fpct`; comparable across stocks |
| Foreign participation ratio | **FL03** | Separates foreign-driven stocks from domestic ones; direction-free |
| Foreign net streak | **FL04** | Prototype `fstreak`, signed here |
| Unusual foreign flow (z / percentile vs own history) | **FL05** | F06 stores it per board only; all-board recomputation verified (`q16`) |
| Accumulation / distribution day count | **FL15** | Separates steady buying from one block day |
| Top-buyer average cost vs close | **FL13** | Prototype `bavg` on real broker prices (gross VWAP = Stockbit Avg) |
| Dominant-buyer persistence | **FL14** | Informed buyers split orders over time (Kyle [18]) |
| Institutional-heavy vs retail-heavy broker net | **FL19** (later) | Current-state class only (`point_in_time_safe = false`) |
| Average trade size and its spike | **FL17** | Trade size as a proxy for larger participants [14][15]; Nego distortion measured |
| Frequency spike | **FL16** | Prototype `freq`; attention and high-volume effects [12][13] |
| Nego/Tunai share of value | **FL18** | Block and crossing activity [16]; the guard the all-board default needs |
| Single broker net (prototype `broker`) | **FL06** | Prototype Broker Follow preset; Backtest `broker` |
| Insider and ≥ 5 % holder net change | **FL20** (later) | Data exists (`q26`); insider purchases are informative [19]; reporting lag |
| Foreign vs domestic divergence | **Rejected (R1)** | Identity: foreign + domestic net = 0 on 1,004/1,004 rows (`q11`); domestic = −foreign |
| Net flow vs price divergence | **Preset, not an indicator (R7)** | It is FL09 or FL01 combined with a price return; the condition engine already combines conditions |

---

### 16.5 The indicators

**Notation.**
- t is the evaluation date, which is the broker as-of date (P10).
- S_D are the last D sessions ≤ t (16.3 calendar).
- For a stock, a broker's D-session values are summed over both investor types and all boards (unless `board` = Regular):
  net n_b, gross buy bv_b, gross sell sv_b, buy lots bl_b.
- V = Σ_b bv_b is the traded value: each trade is counted once, on the buy side.
- Rank brokers by n_b, descending, ties by broker code ascending (as F03 `top_buyer`).
  - B_N = Σ of the positive n_b among the N largest.
  - S_N = Σ of the negative n_b among the N smallest.
- F_s is the all-board foreign investor net on session s: Σ boards of F03 `foreign_net_value`, which equals
  Σ F05 `net_value` where `investor_type` = Foreign.

**Source paths.**
- (a) Direct read of a stored column. It serves only the Regular variant: stored columns are per board.
- (b1) Worker, from the published `broker_window`: F05, 41 sessions, all boards, plus `buy_freq` and `sell_freq`.
- (b2) Worker, from a long all-board series: one row per (ticker, session) with F, V, the Nego+Tunai value and the class nets,
  read per date from F03.
- (b3) Worker, from the insider rows of the events data.
- (c) A new stored feature.

**Live values.** Every distribution and sample is in 16.6; every measured cost is in 16.7.

**Broker lag.** "Broker lag: yes" means the value moves only when broker data is loaded, which is ERRORS M243: one round per
stockbit-updater deployment, no schedule. The cell then carries the broker as-of date (P10).

#### FL01 — Foreign net value (D sessions)

| Field | Content |
|---|---|
| Meaning | How much more foreign investors bought than sold in this stock over the last D sessions, in rupiah. |
| Formula | FL01 = Σ_{s∈S_D} F_s. Default D = 20 (the prototype's foreign presets use `fnet(20)`; the metric's own default is 5). User: D 1-60, `board` All / Regular. |
| Source, grain, unit | F03 `foreign_net_value` (or F05 `net_value`, Foreign); ticker × t; IDR, shown Rp B |
| Condition kinds | VALUE gt / lt / between; EVENT crosses above / below within n; STATE > 0 |
| Interpretation | Positive: foreign investors absorbed shares. Foreign flows are persistent and move prices in emerging markets [7][8]. On IDX, foreign investors have traded at worse prices than domestic ones [9][10], so this is not "smart money" by itself. |
| Misuse warning | Investor type, not broker domicile. Rupiah amounts scale with liquidity, so use FL02 to compare stocks. One Nego block can dominate (CARE 20-day: +376.2 B all boards vs −1.5 B Regular). Differs from Stockbit's Regular-only Foreign Flow (M244). |
| Look-ahead | Sessions ≤ t only; end-of-day data. Safe. |
| Coverage | From 2016-01-04; 832 stocks on 2026-10-27. M157 before September 2020. |
| Broker lag | Yes |
| Path, cost | (b2); also (b1) for D ≤ 20 (verified: the F05 path gives the same distribution to the last digit, `verify_v02_f05_independent.txt`). Backtest `fnet` parity at the default board (all boards, price-bar calendar) except on Nego-only days, which the Backtest skips (corrected; 16.3 calendar). Bounded query `q10` (with FL02, FL04, FL18, FL19): 1.35 s, mostly cold (1,451 blocks read, 651 hit). Production: F03 12-26 ms per date. |

#### FL02 — Foreign net intensity (% of traded value, D sessions)

| Field | Content |
|---|---|
| Meaning | The share of the stock's traded value that foreign investors net bought (or net sold) over D sessions. |
| Formula | FL02 = 100 · Σ_{S_D} F_s / Σ_{S_D} V_s. Default D = 20 (prototype `fpct`). User: D 1-60, board. |
| Source, grain, unit | F03 `foreign_net_value`, `total_buy_value`; ticker × t; %, −100..100 |
| Condition kinds | VALUE; EVENT crosses within n; cross-sectional rank (P7) as a transform |
| Interpretation | Comparable across stocks. +10 % over 20 sessions means foreign investors net took a tenth of all traded value. |
| Misuse warning | Small denominators give extremes (min −99.6, max +96.5): use with the ADV floor. Stored `foreign_net_turnover_ratio_Nd` is per board and must not be added. |
| Look-ahead | Safe |
| Coverage | As FL01; NULL when V = 0. Live (all boards, D 20): median 0.00, p10 −8.69, p90 8.15. (corrected: the median is not 0 because most stocks lack foreign activity; only 7 of 832 had no foreign trade in the 20 sessions. It is near 0 because positive and negative values balance and many are small: \|FL02\| < 1 % on 280 of 832, `verify_v02_f05_independent.txt`, `verify_v08_fl04_streak.txt`.) |
| Broker lag | Yes |
| Path, cost | (b2); `q10` |

#### FL03 — Foreign participation (% of traded value, D sessions)

| Field | Content |
|---|---|
| Meaning | How much of the trading in this stock involves foreign investors on either side, regardless of direction. |
| Formula | FL03 = 100 · Σ_{S_D}(FB_s + FS_s) / (2 · Σ_{S_D} V_s), with FB and FS the foreign gross buy and sell. Default D = 20. User: D 1-20 (from `broker_window`) or 1-60 (if the F06 series is kept). |
| Source, grain, unit | F05 `buy_value`, `sell_value` where Foreign (or F06 `foreign_buy_1d`, `foreign_sell_1d`); ticker × t; %, 0-100 |
| Condition kinds | VALUE |
| Interpretation | High: foreign investors take a large part in price formation. BBCA 62.8 %, CARE 64.8 %, median 9.2 %. Combine with FL02 for direction. |
| Misuse warning | Participation is not demand. A crossing between two foreign clients raises it without any net. |
| Look-ahead | Safe |
| Coverage | As FL01 |
| Broker lag | Yes |
| Path, cost | (b1) after adding no column (values exist in `broker_window`; verified: the F05 path reproduces the F06 distribution exactly, `verify_v02_f05_independent.txt`). Not from Feature 03, which has no foreign gross columns. `q12` (F06, with FL16, FL17): 2.17 s, partly cached (6,520 blocks read, 5,959 hit; corrected from "cold"); F06 is about 20-43× slower per date than F03 (34× on the same date 2026-08-20; corrected from 43×; `q18`, `q24`, `verify_v06_f03_per_date.txt`), so the F05 path is proposed. |

#### FL04 — Foreign net streak (signed)

| Field | Content |
|---|---|
| Meaning | For how many sessions in a row, up to today, foreign investors have been net buyers (positive) or net sellers (negative). |
| Formula | k = the largest k with F_s > 0 on each of the last k sessions → +k; otherwise with F_s < 0 → −k; F_t = 0 → 0. Capped at 60. A session without a trade counts F = 0 and ends the streak. User: cap 1-60, board. |
| Source, grain, unit | F03 `foreign_net_value`; ticker × t; sessions |
| Condition kinds | VALUE ≥ k / ≤ −k; EVENT streak reaches k (prototype preset "Foreign Accumulation Streak": `fstreak > 4` and `fnet(20) > 0`) |
| Interpretation | Persistence of foreign demand [7]. Live max +21, min −27, median 0. |
| Misuse warning | A streak of tiny amounts means little: combine with FL02. The calendar decides whether a non-trading day breaks it (D12). |
| Look-ahead | Safe |
| Coverage | As FL01; needs 61 sessions for the cap |
| Broker lag | Yes |
| Path, cost | (b2); `q10` |

#### FL05 — Foreign flow surprise (own history)

| Field | Content |
|---|---|
| Meaning | How unusual this stock's foreign buying or selling over 20 sessions is compared with its own last year. |
| Formula | X_t = Σ of F over the last 20 ticker sessions. FL05 = percentile of X_t among X_{t−1..t−252} (PROPOSED default), with the F06 mid-rank rule 100 · (#{prev < X_t} + 0.5 · #{prev = X_t}) / 252 (`q02`), or z = (X_t − mean) / sample sd of those 252 (the F06 definition). Today is excluded from the baseline. User: N 5/10/20/40/60, base 252 or 60. (corrected: with base 252, N = 40 and 60 need 292 and 312 ticker sessions, which a 300-market-session series does not give; either cap N at 20 for base 252 or keep about 340 market sessions.) |
| Source, grain, unit | F03 `foreign_net_value` series; ticker × t; percentile 0-100, or σ |
| Condition kinds | VALUE (z ≥ 2, percentile ≥ 95) |
| Interpretation | Highlights stocks whose foreign flow is out of character, independent of size. |
| Misuse warning | Consecutive values overlap (catalog). A single Nego block on a quiet history gives extreme z: live max 157σ. The percentile is bounded and robust, so it is the proposed default. |
| Look-ahead | Safe (baseline excludes t). |
| Coverage | NULL until 272 ticker sessions. Live, inside a 280-market-session window: 723 values, 109 NULL. Full history would give fewer NULLs; Feature 06 has 11 universe stocks with < 252 Regular rows (APPENDIX B §B.2). |
| Broker lag | Yes |
| Path, cost | (b2) with ≥ 272 ticker sessions (≈ 300 market sessions) in the series for N = 20. FACT: one range query planned a parallel seq scan of Feature 03 (12.3 s cold, 96,862 blocks ≈ 757 MB, `q16`); per-date literal reads cost 12-26 ms each cold (5 dates, `q24`, `verify_v06_f03_per_date.txt`), so INFERENCE about 4-8 s of execution for 300 dates. (corrected: "12 ms each, about 3.7 s" rested on one date.) Verified: equals stored F06 Regular z on 38/38 single-board stocks; 66 stocks differ by ≥ 0.5σ between all boards and Regular. |

#### FL06 — Broker net (chosen broker, D sessions)

| Field | Content |
|---|---|
| Meaning | How much one chosen broker's clients net bought in this stock over D sessions. |
| Formula | FL06 = Σ_{S_D} Σ_{investor types, boards} `net_value` of broker X. Defaults D = 5 and X = YP (prototype Broker Follow; P20 a; the Backtest default is YU). User: X from the 112 `IDX_Broker_Profile` codes, D 1-20. |
| Source, grain, unit | F05; ticker × t; IDR |
| Condition kinds | VALUE; EVENT crosses above within n (prototype `xa`) |
| Interpretation | Follows a broker known for a client base. YP's 20-day net in BBCA is +570.1 B. |
| Misuse warning | A broker's net is all its clients together. YP is Retail-heavy with broker type Foreign (`verify_v01_broker_profile.txt`; the class is current-state), so a YP net is mostly retail, not one "bandar", and not foreign investors. |
| Look-ahead | Safe |
| Coverage | From 2016; a broker with no row counts 0 (`flow.ts` `brokerNet`) |
| Broker lag | Yes |
| Path, cost | (b1). Backtest `broker` parity at all boards, except on Nego-only days (16.3 calendar). `q15`: 124 ms for one broker × all stocks × 20 sessions, warm (all 23,913 buffers hit; corrected: no cold figure exists). |

#### FL07 — Top-N broker net accumulation (Rp, D sessions)

| Field | Content |
|---|---|
| Meaning | In rupiah, how much the biggest buying brokers took in, minus what the biggest selling brokers let go, over D sessions. |
| Formula | FL07 = B_N + S_N. Defaults N = 5, D = 10 (prototype `topacc`; Backtest `top5` default `len` 10, `catalog.ts:55`). With N = 5 at all boards it is the Backtest `top5` (`flow.ts:108-121`; corrected from 108-119), up to the calendar (16.3: Nego-only days are skipped there). User: N 1-10, D 1-20. |
| Source, grain, unit | F05; ticker × t; IDR |
| Condition kinds | VALUE; EVENT crosses within n (needs D + n ≤ 41) |
| Interpretation | **Identity (FACT):** the sum of all broker nets is 0 (M154; `q11`). With at least N net buyers and N net sellers, B_N + S_N = −(the net of every other broker). A positive value means the rest of the market sold to the top buyers. |
| Misuse warning | Rupiah amounts scale with liquidity (BBCA −2,153.8 B), so use FL09 to compare stocks. With at most N buyers and N sellers the value is 0 by construction (none on 2026-10-27: at least 11 brokers with a nonzero net, `q13`). |
| Look-ahead | Safe |
| Coverage | From 2016; biased before September 2020 (M157) |
| Broker lag | Yes |
| Path, cost | (b1). `q13` (with FL08-FL13): 3.96 s, partly cached (9,849 blocks read, 17,291 hit; corrected from "cold"), 487,715 rows, 28.6 MB hash-aggregate spill (≈ 53 MB temp written in all). Worker: ≈ 30-40 ms per (D, N) for the whole universe (INFERENCE, `bench_js`). |

#### FL08 — Buy intensity (top-N net buyers, % of traded value)

| Field | Content |
|---|---|
| Meaning | What share of all trading in the stock was net absorbed by its N biggest net buyers over D sessions. |
| Formula | FL08 = 100 · B_N / V. Defaults N = 3, D = 10. A sell-intensity companion 100 · S_N / V is shown beside it. User: N 1-10, D 1-20. |
| Source, grain, unit | F05; ticker × t; %, 0-100 |
| Condition kinds | VALUE |
| Interpretation | The buy side of the bandar balance: FL09 = FL08 + sell intensity. A display option is the "foreign share of the top buyers" of the Terminal's Bandar detector (`verification/terminal_api/DESIGN.md:40`). |
| Misuse warning | It is not aggressor-side buying; no order-side data exists [5]. It is mechanically higher for illiquid stocks: median 24.3 % in the least liquid third vs 12.5 % in the most liquid (`q20`). Read it with FL09 and the ADV floor. |
| Look-ahead | Safe |
| Coverage | As FL07 |
| Broker lag | Yes |
| Path, cost | (b1); `q13` |

#### FL09 — Bandar balance (top-N, % of traded value) — proposed P9 "Bandar"

| Field | Content |
|---|---|
| Meaning | Whether the biggest buying brokers took in more than the biggest selling brokers let go, as a share of all trading. |
| Formula | FL09 = 100 · (B_N + S_N) / V. Defaults N = 3, D = 10 (prototype `bandar(10, 3)`, denominator Σ buy value). States: Big Acc ≥ 10, Acc ≥ 6, Neutral, Dist ≤ −6, Big Dist ≤ −10 (prototype thresholds, per-condition, editable; P22 item 5). User: N 1-10, D 1-20, thresholds. |
| Source, grain, unit | F05; ticker × t; % |
| Condition kinds | STATE (the five states); VALUE; EVENT state change within n |
| Interpretation | By the FL07 identity, FL09 = −(the crowd's net) / V. On 2026-10-27, Big Acc 66, Acc 70, Neutral 607, Dist 52, Big Dist 37 of 832 (`q22`); with ADV ≥ 1 B, 59 of 429 are Acc or Big Acc. It correlates −0.49 to −0.59 with breadth (`q20`; FL09 at D 10, FL12 at D 20): high balance usually comes with few buyers. Verified: computed instead as −100 · (net of every broker outside the top 3 and bottom 3) / V, the distribution is identical, and the sum of all broker nets is 0 for all 832 stocks (`verify_v02_f05_independent.txt`). |
| Misuse warning | The thresholds are a prototype heuristic with no validation. \|FL09\| is larger for illiquid stocks (median 4.43 vs 2.10, `q20`). A Nego block counts as accumulation by the receiving broker: read FL18 beside it. |
| Look-ahead | Safe |
| Coverage | As FL07 |
| Broker lag | Yes |
| Path, cost | (b1); `q13`. All boards vs Regular: 37 of 832 states differ, 0 sign flips (`q23`). |

#### FL10 — Net-buy concentration (HHI) and effective number of net buyers

| Field | Content |
|---|---|
| Meaning | Whether the stock's net buying over D sessions is held by one or two brokers (near 1) or spread over many (near 0). |
| Formula | H = Σ_{b: n_b>0} (n_b / Σ_{n_b>0} n_b)². Effective number of net buyers = 1/H [3]. Default D = 20. User: D 1-20. |
| Source, grain, unit | F05; ticker × t; 0-1 (1/k for k equal buyers) |
| Condition kinds | VALUE; with FL09 as a preset ("few brokers accumulate") |
| Interpretation | The Herfindahl-Hirschman index [1] applied to net accumulation. Live: BBCA 0.095 (10.5 effective buyers), ANTM 0.110 (9.1), CARE 0.401 (2.5). |
| Misuse warning | The merger-guideline levels (0.10 / 0.18 [2], earlier 0.15 / 0.25) describe market structure, not trading: do not reuse them as screen thresholds. Mechanically higher for illiquid stocks (median 0.259 vs 0.204, `q20`). It says who holds the net buying, not whether the net is large: combine with FL09. This is not F03's stored HHI, which is 1-day per board on \|net\|, buyers and sellers mixed. |
| Look-ahead | Safe |
| Coverage | NULL when no broker is a net buyer |
| Broker lag | Yes |
| Path, cost | (b1); `q13` |

#### FL11 — Buy-vs-sell concentration gap

| Field | Content |
|---|---|
| Meaning | Whether buying is done by fewer brokers than selling (positive) or the other way round (negative). |
| Formula | FL11 = Σ_b (bv_b / Σ bv)² − Σ_b (sv_b / Σ sv)² over D. Default D = 20. User: D 1-20. |
| Source, grain, unit | F05; ticker × t; −1..1 |
| Condition kinds | VALUE |
| Interpretation | Few buyers absorbing from many sellers is the classic accumulation picture. Both sides come from the same stock and period, so liquidity partly cancels. Correlation with FL09: 0.22-0.53 (`q20`; FL09 at D 10, FL11 at D 20). |
| Misuse warning | Small values (p10 −0.041, p90 +0.051); dominated by the gross market share of large retail brokers. Later option. |
| Look-ahead | Safe |
| Coverage | As FL07 |
| Broker lag | Yes |
| Path, cost | (b1); `q13` |

#### FL12 — Broker breadth (D sessions)

| Field | Content |
|---|---|
| Meaning | Of the brokers that moved the stock over D sessions, the share that were net buyers. |
| Formula | FL12 = buyers / (buyers + sellers), counted on n_b; brokers with n_b = 0 are left out. Default D = 20. User: D 1-20. EVENT variant: FL12(5) − FL12(20) ≥ x ("breadth turn"). |
| Source, grain, unit | F05; ticker × t; 0-1 |
| Condition kinds | VALUE; EVENT |
| Interpretation | The fraction-of-buyers measure of the LSV herding statistic [4]. Liquidity-neutral: median 0.489 / 0.511 / 0.500 by ADV third (`q20`). Low breadth with a positive FL09 means few brokers buy from many (accumulation). High breadth with a negative FL09 means distribution to many small buyers: BBCA has 0.805 breadth (D 20) and −5.6 % balance (D 10; −3.4 % at D 20). (corrected: the two windows were not named.) |
| Misuse warning | Breadth alone is ambiguous; read it with FL09. F03's `net_buy_broker_ratio` is a different measure: its denominator includes zero-net brokers, and 79 of 865 rows differ (`audit/verify_flow.json` row correction B5). |
| Look-ahead | Safe |
| Coverage | As FL07 |
| Broker lag | Yes |
| Path, cost | (b1); `q13` |

#### FL13 — Top-buyer cost distance (close vs top-N buyer VWAP)

| Field | Content |
|---|---|
| Meaning | How far today's price is above or below the average price the biggest net buyers paid over D sessions. |
| Formula | VWAP = Σ_{top-N net buyers} bv_b / (Σ bl_b × 100) (gross buy VWAP, the Stockbit "Avg"). FL13 = 100 · (close_t / VWAP − 1). Defaults N = 3, D = 10 (prototype `bavg(10)`), **board Regular** (D7). User: N, D 1-20, board. |
| Source, grain, unit | F05 `buy_value`, `buy_lots`; price `close`; ticker × t; % |
| Condition kinds | VALUE between (prototype preset "Near Bandar Average": −3..3 with bandar Acc) |
| Interpretation | Near 0: price is at the top buyers' cost. Below 0: they are under water. A reference price shapes later trading (capital-gains overhang [17]). |
| Misuse warning | On all boards a Nego price can be far from the market (BYAN +275.8 vs −5.3 on Regular end to end, `verify_v05_fl13_regular.txt`; corrected from −5.0, a mixed ranking in `q19`). A broker's buy VWAP covers all its clients' buys, not one position. Across a split, lots and prices mix bases: with P4 A the value is shown with the price-break remark. |
| Look-ahead | Safe, if close_t is the close of the broker as-of date when broker data lags (P10). |
| Coverage | NULL when the top buyers have no lots, and when t has no price bar (a Nego-only day: 4 of the 832 stocks that traded on 2026-10-27; corrected, not stated before). Live all boards: min −62.2 (BAJA, price break), max +275.8. Live Regular end to end (the proposed default): min −32.51, p10 −11.04, median −1.64, p90 5.26, max 22.97 (`verify_v05_fl13_regular.txt`). |
| Broker lag | Yes; it also mixes in price |
| Path, cost | (b1) plus close from the price snapshot; `q13`, `q19` |

#### FL14 — Dominant-buyer persistence

| Field | Content |
|---|---|
| Meaning | On how many of the last D sessions the stock's biggest net buyer was actually buying. |
| Formula | b* = the broker with the largest n_b over D. FL14 = (sessions in S_D with b*'s daily net > 0) / D. Default D = 20. A variant counts the combined top-3. User: D 5-20. |
| Source, grain, unit | F05; ticker × t; 0-1 |
| Condition kinds | VALUE |
| Interpretation | 1.0 means steady buying every session, the pattern of a buyer splitting a large order [18]. Low means one or two block days. Live: BBCA 0.70 (SQ), ANTM 0.60 (YU), CARE 0.20 (AP). |
| Misuse warning | It says nothing about size: use with FL09. F02 `buy_day_ratio_20d` is per investor type and board, and sparse on the latest date, so it is not usable. |
| Look-ahead | Safe |
| Coverage | NULL when no broker is a net buyer |
| Broker lag | Yes |
| Path, cost | (b1). `q14` (with FL15): 1.88 s, all buffers already cached by `q13`; 18.5 MB sort spill. |

#### FL15 — Accumulation-day ratio

| Field | Content |
|---|---|
| Meaning | On what share of the last D sessions the biggest buyers outweighed the biggest sellers. |
| Formula | For each session, b_s = the daily top-N balance (FL09 on one day). FL15 = (sessions with b_s > x) / D; a distribution-day count uses b_s < −x. Defaults N = 3, D = 20, x = 0 (live also shown for x = 5 %). User: N, D 5-20, x. |
| Source, grain, unit | F05; ticker × t; 0-1 (or day counts) |
| Condition kinds | VALUE; EVENT |
| Interpretation | Separates a steady accumulation from one large day inside a window sum. Live median 0.45; CARE 0.85. |
| Misuse warning | Daily balances are noisy; x = 0 counts tiny days. The day count is out of D market sessions: a day without trade counts as no accumulation. On a day with at most N net buyers and N net sellers the daily balance is 0 by construction (the FL07 identity), so that day can never count: 496 of 16,570 traded stock-days (3.0 %) in the 20 sessions; 40 stocks have ≥ 5 such days, 31 of them in the least liquid third (`verify_v04_fl15_identity_days.txt`; corrected, not stated before). |
| Look-ahead | Safe |
| Coverage | As FL07 |
| Broker lag | Yes |
| Path, cost | (b1); `q14`. Worker daily ranking is included in the synthetic 0.25-0.29 s. |

#### FL16 — Trade-count spike

| Field | Content |
|---|---|
| Meaning | How many trades the stock had today compared with its usual number. |
| Formula | trades_s = Σ_b `buy_freq` (= Σ `sell_freq`, FACT). FL16 = trades_t / mean(trades over the 20 sessions before t). Default len 20, all boards. User: len 5-40. |
| Source, grain, unit | F05 `buy_freq` (or F06 `*_buy_freq_1d`); ticker × t; × (ratio) |
| Condition kinds | VALUE; EVENT crosses above x within n (prototype preset "Frequency Spike": crosses 2.5 within 3 with `ret(1) > 0`) |
| Interpretation | Attention or news [12]; unusually high activity tends to precede positive returns [13]. Live median 0.77. (corrected: this is not because 2026-10-27 was quiet; the market had 1,896k trades, 1.075× the prior-20 mean, and the same ratio on 2026-10-23 has a median of 0.695. A per-stock median below 1 follows from skewed daily counts whose mean is pulled up by spikes, `verify_v03_fl16_f05.txt`.) A cross-sectional rank is therefore useful beside the raw ratio. |
| Misuse warning | Counts trades, not value: many small retail trades raise it. The mean of the prior 20 is pulled up by past spikes. |
| Look-ahead | Safe |
| Coverage | Frequency non-null for 4-letter stocks on every sampled date 2016-2026 (`q21`). The Git loader once did not write frequency (`UPDATE_TABLE.md:107-115`); the current importer does. |
| Broker lag | Yes. The price table has no frequency, so this is not a price metric. |
| Path, cost | (b1) after adding `buy_freq` and `sell_freq` to `broker_window`; the Terminal's broker files leave them out (`publisher.py:58-62`). `q12`. Verified: the F05 `buy_freq` path gives the same distribution as the F06 path of `q12`, and buy and sell frequencies balance market-wide on all 21 sessions to 2026-10-27 (`verify_v03_fl16_f05.txt`). |

#### FL17 — Average trade size change

| Field | Content |
|---|---|
| Meaning | Whether the average trade over the last 5 sessions is larger or smaller than over the 20 sessions before. |
| Formula | FL17 = 100 · ((Σ V / Σ trades)_{last 5} / (Σ V / Σ trades)_{prior 20} − 1). **Board Regular** by default (D7). User: windows 5/20, board. |
| Source, grain, unit | F05 `buy_value`, `buy_freq`; ticker × t; % |
| Condition kinds | VALUE |
| Interpretation | A rising ticket size suggests larger participants, as trade-size cutoffs are used to separate institutions [14][15]. |
| Misuse warning | On all boards a Nego block dominates: maximum +13,328 % vs +6,903 % on Regular; average size maximum Rp 2,869 M vs 55.8 M (`q12`). A split changes the per-trade value. |
| Look-ahead | Safe |
| Coverage | As FL16; needs 25 sessions |
| Broker lag | Yes |
| Path, cost | (b1); `q12` |

#### FL18 — Crossing share (Nego + Tunai, % of traded value)

| Field | Content |
|---|---|
| Meaning | How much of the stock's trading went through negotiated and cash-board deals rather than the regular market. |
| Formula | FL18 = 100 · Σ_{S_D} (V_Nego + V_Tunai) / Σ_{S_D} V_all. Default D = 20, plus a 1-day form for block-day events. User: D 1-60. |
| Source, grain, unit | F03 `total_buy_value` per board (or F05); ticker × t; %, 0-100 |
| Condition kinds | VALUE; EVENT (1-day share > x within n) |
| Interpretation | Negotiated deals are often pre-arranged: placements, transfers between related parties, block sales [16]. Under the all-board default it explains how much of FL01 or FL09 came from crossings. Live D = 20: median 0, p90 25.1 %; CARE 54.1 %; BBCA 11.1 %. On 2026-10-27 Nego was 8.7 % of all value. |
| Misuse warning | A crossing is neither accumulation nor distribution by itself: the buyer and seller may be related. Also used as an exclusion filter. |
| Look-ahead | Safe |
| Coverage | As FL01 |
| Broker lag | Yes |
| Path, cost | (b2) or (b1); `q10` |

#### FL19 — Institutional-heavy vs retail-heavy broker net (later)

| Field | Content |
|---|---|
| Meaning | Whether brokers serving mainly institutions were net buying while brokers serving mainly retail clients were net selling, over D sessions. |
| Formula | FL19 = 100 · (Σ_{S_D} inst_net − Σ_{S_D} retail_net) / Σ_{S_D} V. inst_net and retail_net are the nets of brokers classed Institutional-heavy and Retail-heavy. Default D = 20. User: D 1-60. |
| Source, grain, unit | F03 `institutional_net_value`, `retail_net_value`, summed over boards (or F05 + `IDX_Broker_Profile`); ticker × t; % |
| Condition kinds | VALUE |
| Interpretation | Retail net buying has predicted short-run returns as liquidity provision [11]. A positive FL19 is the "institutions in, retail out" reading. |
| Misuse warning | The class is current-state (`point_in_time_safe = false`) and judged by the broker, not the client. Retail-heavy includes foreign-type brokers (9 of 19, among them YP, ZP, YU, KK, DR; `verify_v01_broker_profile.txt`). Range −199..113 % (two opposite nets). |
| Look-ahead | **Not safe for past dates.** NA for evaluation dates before the profile's validity. Current date only. |
| Coverage | 25 / 23 / 45 / 19 brokers per class |
| Broker lag | Yes |
| Path, cost | (b2) or (b1); `q10` |

#### FL20 — Insider and major-holder net change (later)

| Field | Content |
|---|---|
| Meaning | Whether company insiders or ≥ 5 % holders reported net buying or selling of the stock recently. |
| Formula | Insider net value = Σ `value_idr` of `action` BUY − Σ `value_idr` of SELL for IDX-origin movements with transaction date (`annotation_date`, role TRANSACTION_DATE) in the last D sessions. Major-holder net = Σ `pct_change` of KSEI-origin movements. Default D = 20. User: D, origin, roles (`holder_role` DIREKTUR, KOMISARIS, PENGENDALI). |
| Source, grain, unit | `idx_event_annotation` insider rows (published per ticker, `publisher.py:27`); ticker × t; IDR and percentage points |
| Condition kinds | VALUE; EVENT (a new insider BUY within n) |
| Interpretation | Insider purchases are informative about future returns [19]. |
| Misuse warning | The transaction date is not the date the market learned it: reports come later. KSEI dates are position-report dates; many KSEI prices are Stockbit estimates (`is_estimated_price`). |
| Look-ahead | **Not point-in-time** for past dates. (corrected: `first_seen_at`, the first pull, exists only on the raw `stockbit_insider_transaction`, which the publisher cannot read (`q26`); the published `idx_event_annotation` has only `source_fetched_at`, the latest pull, and `ingestion_time` (`DATABASE_SCHEMA.md` idx_event_annotation). On path (b3) there is no first-seen time at all, and even `first_seen_at` would only bound publication from above, since pulls are ad hoc.) |
| Coverage | IDX since 2019-11, KSEI since 2017-10 (`q26`). Loaded ad hoc with a user token (`UPDATE_TABLE.md` part B), so it has its own lag. Not broker data. |
| Broker lag | No (its own load lag) |
| Path, cost | (b3) from the Phase 1 `actions` cross-section extended with insider rows; not measured (104k rows in total). |

---

### 16.6 Live distributions, 2026-10-27 (FACT)

- Population: universe stocks ("Security Type" = stock) with a row on some board on 2026-10-27. 832 stocks, or 828 where a
  close is needed. (corrected: FL07-FL12 also use the 828, because `q13` joins the price for every metric; the
  verification recomputed them on the same 828.)
- Market sessions: D5 from 2026-10-21, D10 from 2026-10-14, D20 from 2026-09-30, D25 from 2026-09-23
  (`q07_calendar_long.txt`).
- Samples: BBCA (ADV20 Rp 1,872.9 B), ANTM (Rp 267.2 B), CARE (Rp 48.1 B; heavy Nego).

| Indicator (parameters) | n | min | p10 | median | p90 | max | BBCA | ANTM | CARE | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| FL01 foreign net, D 20, Rp B | 832 | −5,535.48 | −11.04 | 0.00 | 3.19 | 1,528.09 | −5,535.48 | −477.11 | 376.22 | `q10` |
| FL01 foreign net, D 5, Rp B | 832 | −1,215.65 | −3.48 | −0.003 | 0.59 | 376.75 | −1,215.65 | −299.79 | 376.75 | `q10` |
| FL01 reference: Regular, D 20, Rp B | 832 | −5,509.31 | −9.77 | 0.00 | 1.98 | 217.67 | −5,509.31 | −477.18 | −1.50 | `q10` |
| FL02 foreign net % of value, D 20 | 832 | −99.64 | −8.69 | 0.00 | 8.15 | 96.46 | −14.78 | −8.93 | 39.12 | `q10` |
| FL02 reference: Regular | 831 | −77.15 | −9.52 | 0.00 | 6.82 | 77.20 | −16.55 | −8.99 | −0.34 | `q10` |
| FL03 foreign participation %, D 20 | 832 | 0.00 | 1.76 | 9.22 | 37.05 | 99.72 | 62.78 | 36.19 | 64.77 | `q12` |
| FL04 foreign streak, sessions | 832 | −27 | −4 | 0 | 2 | 21 | −4 | −6 | −4 | `q10` |
| FL05 foreign net 20 z vs prior 252 | 723 (109 NULL) | −10.33 | −0.91 | 0.10 | 1.13 | 157.13 | −0.69 | −0.29 | 1.14 (Regular stored 0.17) | `q16` |
| FL06 broker YP net, D 20, Rp B | 832 | −75.73 | −1.24 | 0.00 | 1.43 | 570.12 | 570.12 | −8.30 | −0.002 | `q15` |
| FL06 broker YP net, D 5, Rp B | 832 | −155.72 | −0.49 | 0.00 | 0.43 | 114.10 | 114.10 | −9.39 | −0.003 | `q15` |
| FL07 top-5 net, D 10, Rp B | 828 | −2,153.83 | −1.25 | 0.004 | 1.99 | 346.73 | −2,153.83 | −106.16 | 0.15 | `q13` |
| FL08 buy intensity top 3, D 10, % | 828 | 0.09 | 4.94 | 16.41 | 46.14 | 99.20 | 10.11 | 6.96 | 2.19 | `q13` |
| FL08 companion: sell intensity top 3, D 10, % | 828 | −99.20 | −42.10 | −16.22 | −4.85 | −0.06 | −15.73 | −8.65 | −2.16 | `q13` |
| FL09 bandar balance top 3, D 10, % | 828 | −32.63 | −6.31 | 0.29 | 8.78 | 29.40 | −5.62 | −1.69 | 0.03 | `q13` |
| FL09 bandar balance top 3, D 20, % | 828 | −33.93 | −5.13 | 0.31 | 7.51 | 32.17 | −3.42 | −1.85 | 1.26 | `q13` |
| FL10 net-buy HHI, D 20 | 828 | 0.060 | 0.118 | 0.222 | 0.611 | 0.999 | 0.095 | 0.110 | 0.401 | `q13` |
| FL10 effective net buyers (1/HHI) | 828 | 1.00 | 1.64 | 4.50 | 8.49 | 16.66 | 10.54 | 9.13 | 2.50 | `q13` |
| FL11 buy−sell HHI gap, D 20 | 828 | −0.534 | −0.041 | 0.004 | 0.051 | 0.572 | −0.016 | −0.0001 | 0.061 | `q13` |
| FL11 reference: gross buy HHI, D 20 | 828 | 0.037 | 0.078 | 0.154 | 0.303 | 0.994 | 0.073 | 0.072 | 0.779 | `q13` |
| FL12 breadth, D 20 | 828 | 0.108 | 0.347 | 0.500 | 0.648 | 0.850 | 0.805 | 0.563 | 0.452 | `q13` |
| FL13 close vs top-3 VWAP, D 10, all boards, % | 828 | −62.19 | −11.32 | −1.84 | 5.83 | 275.84 | −4.72 | 2.45 | 8.34 | `q13` |
| FL13 Regular end to end (proposed default, D7), % (added by verification) | 828 | −32.51 | −11.04 | −1.64 | 5.26 | 22.97 | −4.45 | — | −11.17 | `verify_v05` |
| FL14 top-1 buyer buy-day ratio, D 20 | 832 | 0.05 | 0.25 | 0.60 | 0.80 | 1.00 | 0.70 (SQ) | 0.60 (YU) | 0.20 (AP) | `q14` |
| FL15 accumulation-day ratio, x = 0, D 20 | 832 | 0.00 | 0.25 | 0.45 | 0.65 | 0.95 | 0.40 | 0.40 | 0.85 | `q14` |
| FL15 days with balance ≥ +5 % (of 20) | 832 | 0 | 1 | 4 | 8 | 19 | 3 | 5 | 8 | `q14` |
| FL15 days with balance ≤ −5 % (of 20) | 832 | 0 | 2 | 5 | 10 | 17 | 8 | 9 | 1 | `q14` |
| FL16 trade-count spike, all boards, × | 832 | 0.001 | 0.293 | 0.773 | 1.763 | 49.24 | 1.641 | 1.118 | 0.924 | `q12` |
| FL16 reference: Regular | 831 | 0.000 | 0.293 | 0.774 | 1.785 | 49.25 | 1.641 | 1.118 | 0.923 | `q12` |
| FL17 trade-size change 5 vs 20, all boards, % | 832 | −99.67 | −58.83 | −16.01 | 58.65 | 13,327.7 | −16.20 | −4.69 | −1.38 | `q12` |
| FL17 Regular (proposed default), % | 830 | −95.37 | −51.49 | −15.23 | 38.76 | 6,903.2 | −16.26 | −4.10 | −33.73 | `q12` |
| FL17 reference: average trade size, D 20, all boards, Rp M | 832 | 0.066 | 0.58 | 1.62 | 10.34 | 2,869.0 | 35.77 | 12.40 | 91.99 | `q12` |
| FL17 reference: average trade size, D 20, Regular, Rp M | 831 | 0.066 | 0.55 | 1.48 | 7.45 | 55.77 | 31.81 | 12.32 | 42.38 | `q12` |
| FL18 crossing share, D 20, % | 832 | 0 | 0 | 0 | 25.09 | 100 | 11.13 | 0.64 | 54.10 | `q10` |
| FL18 crossing share, 1 day, % | 832 | 0 | 0 | 0 | 0.003 | 100 | 19.73 | 0.008 | 76.25 | `q10` |
| FL19 inst − retail net % of value, D 20 | 832 | −199.27 | −15.65 | −0.12 | 17.94 | 113.34 | −18.89 | −2.59 | −2.67 | `q10` |
| Context: ADV20 all boards, Rp B | 832 | 0.001 | 0.057 | 1.109 | 28.63 | 1,872.87 | 1,872.87 | 267.25 | 48.09 | `q10` |

**Notes on the table.**
- FL20 has no distribution. Its live counts are in 16.2 (`q26`).
- FL13 on Regular: 31 stocks differ by more than 5 points from the all-board value (`verify_v05`; corrected from 34 in
  `q19`, whose "Regular" ranked the top buyers on all-board nets).
- FL05 runs on ticker sessions inside a 280-market-session window. Its NULL count is therefore higher than full history would
  give.

---

### 16.7 Cost

#### 16.7.1 Whole-universe bounded measurements at 2026-10-27 (FACT, `EXPLAIN (ANALYZE, BUFFERS)` and actual runs)

These are direct SQL computations of the indicators. They measure the work involved; they are not the production path, which
reads per date and computes in the worker (16.7.2).

| Query | Indicators | Window, rows | Plan | Execution (EXPLAIN run) | Re-run round trip | Blocks read | Spill | Evidence |
|---|---|---|---|---|---|---|---|---|
| Feature 03 all-board window | FL01, FL02, FL04, FL18, FL19 | 61 sessions (2026-07-31..10-27), 68,865 rows | Bitmap index scan on `date_board_ticker_idx` | 1,351 ms | 606 ms | 1,451 (651 hit) | 8.4 MB temp written (17.7 MB read) | `q10_f03_window61_*` |
| Feature 06 all-board window | FL03, FL16, FL17 | 25 sessions (09-23..10-27), 24,465 rows | pkey index scan, 1,797 index searches | 2,168 ms | 335 ms | 6,520 (5,959 hit) | none | `q12_f06_window25_*` |
| Feature 05 per (ticker, broker) | FL07-FL13 | 20 sessions (09-30..10-27), 487,715 rows | `trade_date_idx` scan; HashAggregate 65 batches | 3,956 ms | 847 ms | 9,849 (17,291 hit) | 28.6 MB hash-aggregate spill; 52.8 MB temp written in all | `q13_f05_broker20_*` |
| Feature 05 daily ranking | FL14, FL15 | 20 sessions, 487,715 rows | external merge sort | 1,885 ms (buffers already cached by `q13`) | 1,737 ms | 0 (26,147 hit) | 18.5 MB sort spill; 37.9 MB temp written in all | `q14_f05_daily20_*` |
| Feature 05 one broker | FL06 | 20 sessions, about 18k rows kept | parallel index scan with a filter | 124 ms | 305 ms | 0 (23,913 hit) | none | `q15_f05_one_broker20_*` |
| Feature 03 long series | FL05 | 280 sessions (2025-08-29..2026-10-27), 374,928 rows | **parallel seq scan of Feature 03** (planner choice) | 12,306 ms | 2,854 ms | 96,862 (≈ 757 MB) | ≈ 13 MB | `q16_f03_zscore280_*` |
| Board-effect checks | FL09, FL13 | 10 sessions | as `q13` | — | 959-1,117 ms | cached | — | `q19`, `q20`, `q22`, `q23` |

- The re-runs are best case from the OS cache. The flow verification measured 3-8 s, with one timeout, for multi-date
  F05/F06 aggregates on this 128 MB buffer pool (`audit/verify_flow.json` refuted C12).
- (corrected: the "Blocks read" column counts only blocks read from outside shared buffers; the hits are now shown. Only
  `q10` and `q16` were mostly cold; `q12` and `q13` were about half cached, `q14` and `q15` fully. The temp column
  mixed read and written figures; it now gives temp written. Verification re-runs, 2026-10-28 13:55-14:20 UTC: an
  independent F05 recomputation of eight distributions took 5.6 s, re-runs of `q14`, `q20`, `q22` and `q11` returned
  identical results.)
- PROPOSED: no screen request runs these aggregates. That is consistent with TARGET ARCHITECTURE §6.11 "options rejected".

#### 16.7.2 Production path cost per publication

**Per-date reads, FACT** (`q17_per_date_reads.txt`, `q18_per_date_reads_cold.txt`, `q24_f03_per_date_cold.txt`; verification
`verify_v06_f03_per_date.txt`, `verify_v07_f05_per_date.txt`):

| Table, one date | Rows | Cold | Warm | Blocks read cold |
|---|---|---|---|---|
| Feature 05 (2026-08-20) | 26,786 | 1,824 ms | 6.7 ms (2026-10-23) | 1,713 |
| Feature 05 (2026-06-10, verification) | about 27k | 1,680 ms | — | 1,769 |
| Feature 06 (2026-08-20) | 1,446 | 524 ms | 104 ms (2026-10-23, partly cached) | 1,439 (one block per row) |
| Feature 03 (2025-03-14) | 1,170 | 12.3 ms | 6.8 ms | 41 |
| Feature 03 (2025-09-15, 2025-12-10, 2026-05-20, 2026-08-20; verification) | 1,242-1,446 | 15.4-26.4 ms | — | 43-48 |

**Files and work (INFERENCE from the reads, except where marked).**

| File / work | Content | Build from scratch | Incremental (new or revised dates only) | Size |
|---|---|---|---|---|
| `broker_window` (design §6.11, plus `buy_freq`, `sell_freq`) | F05 rows of 41 sessions, all boards | 41 F05 dates: between ≈ 8 s (the 20 dates of `q13` read 9,849 blocks in 3.96 s) and ≈ 75 s fully cold (41 × 1.8 s) | ≈ 2 s per new date | ≈ 1.0 M rows; 8-12 MB gzip (design INFERENCE), plus two integer columns |
| All-board series (replaces the long F06 series of `flow_f06` for FL01, FL02, FL04, FL05, FL18, FL19) | Per (ticker, session): F, V, Nego+Tunai value, inst and retail net; about 300 sessions | 300 F03 dates × 12-26 ms ≈ 4-8 s cold (corrected from "× 12 ms ≈ 3.7 s", one date) | ≈ 12-26 ms | 850 × 300 × 5 numbers; a few MB gzip (UNKNOWN until measured, U4) |
| Same series from Feature 05 instead (no new grant) | as above | 300 × 1.8 s ≈ 9 min one-off | ≈ 2 s per date | as above |
| Worker CPU, broker grid (D 5/10/20 × N 3/5 and the daily ranking for FL14/FL15) | whole universe | FACT, synthetic: 245-289 ms per pass on one core, 1.6 M random rows (`bench_js/worker_cost.mjs`, `worker_cost.txt`) | same | — |
| Worker CPU, a custom (D, N) on request | whole universe | ≈ 30-40 ms (INFERENCE: the grid's time divided by its 8 passes) | — | — |
| FL20 | insider rows of the events data | Phase 1 `actions` read plus insider rows; not measured | — | small |

- Revised dates: a round can rewrite old dates. The UPDATE_TABLE refresh derives `p_from` from the data, and
  `Monitoring_Stockbit_Update.broker_dates` lists the round's dates. So an incremental build must re-read the dates a round
  changed (INFERENCE).
- Total per publication (INFERENCE): about 2 s of database time incremental. From scratch, about 12-85 s, dominated by F05,
  plus under 0.5 s of worker CPU. TARGET ARCHITECTURE §6.11 estimated 10-40 s of DB time for the F06-based plan; F06 per date
  is about 20-43× slower than F03 (34× on the same date, 2026-08-20). (corrected: "12-80 s" and "43×" rested on one F03
  date.) Round trips per statement come on top; the publisher's direct connection makes them small (INFERENCE).

---

### 16.8 Ranking

**Recommended first set: 11 indicators (PROPOSED).**

| Rank | Indicator | Why first |
|---|---|---|
| 1 | FL09 Bandar balance (top 3, 10 sessions) | The prototype's `bandar`, the proposed P9 definition, and the bandarmology premise as an identity; normalised |
| 2 | FL01 Foreign net value | Prototype `fnet`; Backtest `fnet` at all boards, lossless except on Nego-only days, which the Backtest's price-bar calendar skips (corrected; 16.3) |
| 3 | FL02 Foreign net intensity | Normalised foreign flow, comparable across stocks |
| 4 | FL07 Top-N net accumulation (Rp) | Prototype `topacc`; Backtest `top5` at N = 5; same pass as FL09 |
| 5 | FL08 Buy intensity | The user's example; buy side of FL09, same pass |
| 6 | FL10 Net-buy HHI + effective buyers | The user's example; who holds the accumulation |
| 7 | FL12 Broker breadth | Liquidity-neutral; disambiguates FL09 |
| 8 | FL06 Broker net (chosen broker) | Prototype Broker Follow; Backtest `broker` |
| 9 | FL04 Foreign streak | Prototype `fstreak` preset |
| 10 | FL16 Trade-count spike | Prototype `freq` preset |
| 11 | FL18 Crossing share | The guard the all-board default needs; same read as FL01 |

- Cost of the first set: one `broker_window` pass and one all-board series. No new stored feature.
- If 10 are wanted, FL04 moves to the later options.
- Verification note (duplicates, PROPOSED alternative): FL07 is FL09's numerator in rupiah (FL07 = FL09 · V / 100 at the same
  N and D) and FL01 is FL02 in rupiah; FL08 is the buy half of FL09. They are kept for prototype and Backtest parity, not
  because they measure something different. If the set must shrink, FL07 and FL01 can become a unit option (Rp or %) of
  FL09 and FL02 instead of separate indicators, which keeps FL04.

**Later options (9).**
- FL13 cost distance: after decision D7 and the price-break remark.
- FL14 persistence and FL15 accumulation days: after FL09 is in use.
- FL05 surprise: needs the 300-session series.
- FL03 participation.
- FL17 trade size: Regular default, D7.
- FL11 HHI gap: overlaps with FL09, FL10 and FL12.
- FL19 class net: not point-in-time.
- FL20 insider: a different source and lag.

**Rejected (9, with why).**

| # | Candidate | Why |
|---|---|---|
| R1 | Foreign vs domestic divergence | Foreign + domestic net = 0 on 1,004/1,004 rows (`q11`; M154 from 2021): no information |
| R2 | Stock-level total buy − total sell ("net accumulation") | Identically 0 by construction (M154; F03 catalog) |
| R3 | Aggressor-side order imbalance [5], PIN [6], VPIN, buy-volume ratio | Need buyer/seller-initiated trades; no per-trade side exists |
| R4 | Order-book depth, queue, bid-ask metrics | No order book |
| R5 | Ownership concentration or free-float change | No full register; only FL20's movements |
| R6 | F03 stored HHI, `top3_buyer_share` or `net_buy_broker_ratio` averaged or summed across boards | Non-additive (allowed aggregations have no SUM, `q01`); \|net\| HHI mixes both sides; replaced by FL10 and FL12 |
| R7 | Net flow vs price divergence as its own formula | It is a combination of FL09 or FL01 with a price return; offered as a preset ("Accumulation on weakness": FL09 ≥ 6 and ret(10) < 0) |
| R8 | Foreign-broker (domicile) flow | Domicile is not the investor: YP is broker type Foreign but Retail-heavy (`verify_v01_broker_profile.txt`; corrected pointer, `q21` shows the class only); the catalog forbids the reading |
| R9 | Prototype `bavg` as coded (net-weighted typical price) and F02 latest-date rolling columns | Real broker prices exist (FL13 gross VWAP); F02 is sparse on the latest date (−408 vs −477 B, APPENDIX B §B.3) |

**Presets built from the set (PROPOSED; thresholds unvalidated).**
- "Quiet accumulation": FL09 ≥ 6, FL12 < 0.5, FL14 ≥ 0.6.
  - FACT: 119 stocks meet FL09 ≥ 6 and FL12 < 0.5 on 2026-10-27; 51 of them have ADV ≥ 1 B (`q22`).
- "Foreign accumulation, unusual": FL02(20) ≥ 3 and FL05 ≥ 95th percentile. (Not counted: the percentile form of FL05 was
  not measured live; only its z form was, 16.6.)
- "Accumulation, not a crossing": FL09 ≥ 6 and FL18(20) < 10.
- "Accumulation near cost": FL09 ≥ 6 and FL13 between −3 and 3.
- "Accumulation on weakness" (R7).

---

### 16.9 Snapshots, files or features needed, and the total per publication

- **No new stored feature (c) is required** for FL01-FL20 (PROPOSED).
- **Needed, all PROPOSED and awaiting "go":**
  1. `broker_window` gains two columns, `buy_freq` and `sell_freq`, for FL16 and FL17. It is a new file, so the Terminal's
     broker files stay unchanged.
  2. A long all-board series of about 300 sessions from **Feature 03** for FL01, FL02, FL04, FL05, FL18 and FL19. It needs
     SELECT on Feature 03 for the publisher's read group, through a forward migration. Today the publisher has F05 and
     `IDX_Broker_Profile` but not F03 or F06 (`q25`).
     - Feature 03 is the better source: 12-26 ms and 41-48 blocks per date cold (5 dates), against 524 ms and 1,439 blocks
       for Feature 06 (corrected from "12 ms and 41 blocks", one date).
     - It is written per date after all of Feature 02 (`apps/stockbit-updater/refresh.py:129-130`, `audit/verify_flow.json`
       additional findings), so a date is present for all tickers or for none (INFERENCE).
     - The design's completeness gate can then compare the Feature 03 Regular row count with the Feature 05 Regular tickers.
       Both files must be cut at the same complete date: during a round F05 holds the new date before F03 does
       (`audit/verify_flow.json` additional finding 4).
     - Without the grant, the same series comes from F05: about 9 minutes one-off (300 × 1.7-1.8 s), then about 2 s per date.
     - Series length: 300 market sessions serve FL05 up to N = 20 with base 252; N = 40 or 60 needs about 340 (16.5 FL05).
  3. FL20: insider rows in the Phase 1 `actions` cross-section.
- **Total per publication (INFERENCE):** about 2 s of DB time incremental, about 12-85 s from scratch (corrected from 12-80 s), under 0.5 s of worker
  CPU. Files: about 8-12 MB plus a few MB gzip.
- **Option (c) for later:** an all-board daily flow Feature, grain (ticker, date), holding FL01, FL02, FL05, FL07-FL10 and
  FL12. It would be worth it if the AI should read these indicators, or if FL09 thresholds are to become own-history
  percentiles (that needs 252 sessions of daily rankings, which the window files do not keep). It needs the onboarding plan
  (`NEW_TABLE_ONBOARDING_PLAN.md`) and the catalog wording of 16.3.

---

### 16.10 Impact on the existing design (TARGET ARCHITECTURE §6.11)

1. **Grant (PROPOSED change).** The design grants SELECT on Feature 06 and reads `flow_f06` series per date. With P8 = all
   boards, the stored per-board F06 columns serve only the Regular variant and the self-check. Recommendation:
   - grant Feature 03 instead, or in addition;
   - build the long series from Feature 03;
   - take the gross foreign and frequency components for D ≤ 25 from `broker_window`.
   A 312-session F06 series would cost about 312 × 0.52 s ≈ 160 s cold, against about 5-8 s from F03 (16.7.2; corrected
   from about 4 s).
2. **Send to Backtest.** At the all-board default, `fnet` (FL01), `broker` (FL06) and `top5` (FL07 with N = 5) transfer
   with the same formula. (corrected: not losslessly in every case; the Backtest runs on price bars and skips broker rows on
   Nego-only days, 81 stock-days of 15 stocks in the 20 sessions to 2026-10-27, e.g. TRUK +130.5 B of foreign net,
   `verify_v14_nego_only_days.txt`; the card should say so for those stocks.) Any other N, the Regular variant and
   FL02-FL05 and FL08-FL20 have no Backtest condition yet.
3. **Self-check.** Already verified: F03 = F06 on 1,004/1,004 rows for the net and the value (`q11`). FL05's method equals
   the stored F06 Regular z on 38/38 single-board stocks (`q16`). Both can become fixtures.
4. **`topNAccumulation`.** It serves FL07-FL09 and FL13-FL15 through one ranking. The design's TEMPORARY copy rule
   (`flow.ts` content hash) applies.

---

### 16.11 Decisions for the user

The ids D1-D14 are local to this section (cited elsewhere as "16.11 D7"); they are not `ERRORS_AND_SOLUTIONS.md` D-layer ids.

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | Which indicators ship in Phase 2 | First set of 11 (16.8), a subset, or more | The 11 of 16.8; the later 9 as a Phase 2b list |
| D2 | P9: is "Bandar" one of these, and which | (a) FL09, N 3, D 10, all boards, % of value, states ±6/±10 per condition; (b) a composite (FL09 + FL12 + FL14); (c) another definition | (a). Composites stay presets. "Bandar average price" = FL13 (gross VWAP of the top 3). The Terminal detector uses the same definition. Thresholds are labelled unvalidated. |
| D3 | HHI basis | (a) net-buy HHI (FL10); (b) gross buy HHI; (c) \|net\| HHI as F03; (d) buy−sell gap (FL11) | (a), with the effective number of buyers shown; (d) as a later option |
| D4 | Buy intensity definition | (a) top-N net buyers' net / traded value (FL08); (b) top-N gross buy share | (a); (b) mostly measures broker market share |
| D5 | Default windows | Broker ranking D 10 (FL07-FL09, FL13); concentration, breadth and persistence D 20 (FL10, FL12, FL14, FL15); foreign D 20 (FL01-FL03, FL05); FL06 D 5; or one D for all | As listed (prototype parity). Ranges: broker D 1-20, foreign D 1-60. |
| D6 | Top-N | N 3 for FL08, FL09, FL13; N 5 for FL07 (Backtest `top5`); range 1-10 | As listed |
| D7 | Board exceptions to P8 | (a) FL13 (VWAP) and FL17 (trade size) default to Regular, labelled; (b) all boards everywhere with FL18 beside them | (a): measured Nego distortion (31 of 828 VWAP distances move > 5 points, Regular end to end; corrected from 34; ticket-size maximum Rp 2,869 M vs 55.8 M). Every indicator keeps a `board` parameter All / Regular (Stockbit comparison, M244). |
| D8 | FL05 form | (a) own-history percentile; (b) z-score as F06 | (a): bounded, robust to blocks (live z max 157σ). Its live distribution was not measured (only the z form, 16.6). |
| D9 | Publisher data source for the long series | (a) SELECT on Feature 03 by forward migration; (b) F06 as designed; (c) F05 only, no new grant | (a): about 20-43× cheaper per date than F06 (34× on the same date; corrected from 43×); (c) if no grant is wanted (≈ 9 min one-off backfill) |
| D10 | Threshold style | (a) fixed thresholds with the ADV floor on; (b) liquidity-relative or own-history percentiles (needs option c of 16.9) | (a) now, with the liquidity dependence disclosed on FL08, FL09 and FL10; (b) later |
| D11 | FL19 and FL20 | Include (current date only for FL19; reporting-lag remark for FL20), or leave out | Later options, not in the first set |
| D12 | Calendar (P20 b) | Market sessions for the window metrics (as measured here) and ticker sessions for FL05 (F06 parity); or the Backtest's price bars | Market sessions plus ticker sessions for FL05, labelled; the Backtest calendar only inside Send to Backtest. The price-bar calendar also drops Nego-only days (81 stock-days of 15 stocks in 20 sessions), so a sent condition can read a different value for those stocks (verification, 16.3). |
| D13 | Default broker for FL06 (P20 a) | YP (prototype) or YU (Backtest) | YP, with the broker shown on the card (as P20) |
| D14 | Broker lag (P10) | As UNKNOWNS P10 | P10 (a): evaluate at the broker as-of date, labelled; FL13 uses the close of that date |

---

### 16.12 References

These references give each measure's definition and its known behaviour. They come from the literature; none was fetched or
re-checked in this task (no external call was made), and none validates a threshold on IDX broker-summary data.

1. Herfindahl, O. C. (1950). *Concentration in the Steel Industry*. PhD dissertation, Columbia University. Hirschman, A. O.
   (1964). "The paternity of an index." *American Economic Review* 54(5).
2. U.S. Department of Justice and Federal Trade Commission (2023). *Merger Guidelines*, §2.1 (HHI above 1,800 = highly
   concentrated). Earlier: *Horizontal Merger Guidelines* (2010), §5.3 (1,500 / 2,500).
3. Adelman, M. A. (1969). "Comment on the 'H' concentration measure as a numbers-equivalent." *Review of Economics and
   Statistics* 51(1).
4. Lakonishok, J., Shleifer, A. and Vishny, R. (1992). "The impact of institutional trading on stock prices." *Journal of
   Financial Economics* 32(1).
5. Chordia, T., Roll, R. and Subrahmanyam, A. (2002). "Order imbalance, liquidity, and market returns." *Journal of Financial
   Economics* 65(1).
6. Easley, D., Kiefer, N., O'Hara, M. and Paperman, J. (1996). "Liquidity, information, and infrequently traded stocks."
   *Journal of Finance* 51(4).
7. Froot, K., O'Connell, P. and Seasholes, M. (2001). "The portfolio flows of international investors." *Journal of Financial
   Economics* 59(2).
8. Richards, A. (2005). "Big fish in small ponds: The trading behavior and price impact of foreign investors in Asian emerging
   equity markets." *Journal of Financial and Quantitative Analysis* 40(1).
9. Dvořák, T. (2005). "Do domestic investors have an information advantage? Evidence from Indonesia." *Journal of Finance*
   60(2).
10. Agarwal, S., Faircloth, S., Liu, C. and Rhee, S. G. (2009). "Why do foreign investors underperform domestic investors in
    trading activities? Evidence from Indonesia." *Journal of Financial Markets* 12(1).
11. Kaniel, R., Saar, G. and Titman, S. (2008). "Individual investor trading and stock returns." *Journal of Finance* 63(1).
12. Barber, B. and Odean, T. (2008). "All that glitters: The effect of attention and news on the buying behavior of individual
    and institutional investors." *Review of Financial Studies* 21(2).
13. Gervais, S., Kaniel, R. and Mingelgrin, D. (2001). "The high-volume return premium." *Journal of Finance* 56(3).
14. Lee, C. and Radhakrishna, B. (2000). "Inferring investor behavior: Evidence from TORQ data." *Journal of Financial
    Markets* 3(2).
15. Campbell, J., Ramadorai, T. and Schwartz, A. (2009). "Caught on tape: Institutional trading, stock returns, and earnings
    announcements." *Journal of Financial Economics* 92(1).
16. Holthausen, R., Leftwich, R. and Mayers, D. (1987). "The effect of large block transactions on security prices: A
    cross-sectional analysis." *Journal of Financial Economics* 19(2).
17. Grinblatt, M. and Han, B. (2005). "Prospect theory, mental accounting, and momentum." *Journal of Financial Economics*
    78(2).
18. Kyle, A. (1985). "Continuous auctions and insider trading." *Econometrica* 53(6).
19. Lakonishok, J. and Lee, I. (2001). "Are insider trades informative?" *Review of Financial Studies* 14(1).

**UNKNOWN.**
- The formula of Stockbit's own Bandar Detector: it is not in the repository and was not checked. Check: Stockbit's help or a
  sample comparison against FL09.
- Whether IDX's public foreign net uses all boards (UNKNOWNS U5).
- Every threshold's predictive value. Check: a Backtest run once the indicators exist there.

---

### 16.13 Evidence (`evidence/flow_proposals/`)

| File | What it holds |
|---|---|
| `q00_catalog_cols.*`, `q01_catalog_f03_f05.*`, `q02_catalog_f06_f02.*` | Feature_Catalog columns, and the F03, F05, F06 and F02 rows: formula, allowed aggregations, point-in-time flag, misuse warning |
| `q03_state_calendar.*`, `q04_monitoring.*`, `q05_universe.*`, `q06_types.*`, `q07_calendar_long.*` | Latest dates, monitoring rows, universe and board coverage, column types, session calendar |
| `q10_f03_window61.sql`, `_explain_run1.txt`, `_result.txt` | FL01, FL02, FL04, FL18, FL19: SQL, plan, distribution |
| `q11_f03_vs_f06_latest.*` | F03 = F06; F + D = 0; buy freq = sell freq (1,004 rows) |
| `q12_f06_window25.*` | FL03, FL16, FL17 |
| `q13_f05_broker20.*` | FL07-FL13 |
| `q14_f05_daily20.*` | FL14, FL15 |
| `q15_f05_one_broker20.*` | FL06 |
| `q16_f03_zscore280.*` | FL05, parity with stored F06 z |
| `q17_per_date_reads.*`, `q18_per_date_reads_cold.*`, `q24_f03_per_date_cold.*` | Per-date read costs of F05, F06 and F03 |
| `q19_vwap_board_effect.*` | FL13 all boards vs Regular (its Regular ranks the top buyers on all-board nets; Regular end to end is `verify_v05`) |
| `q20_liquidity_dependence.*` | FL08-FL12 by ADV third |
| `q21_freq_coverage_sample.*` | Frequency nulls by year; broker classes |
| `q22_bandar_state_counts.*`, `q23_board_effect_bandar.*` | FL09 state counts; board effect on states and top buyer |
| `q25_publisher_grants.*` | Publisher login SELECT on the flow tables |
| `q26_insider_coverage.*` | Insider and KSEI coverage |
| `q27_f05_latest_shape.*` | F05 rows, brokers and value per board on 2026-10-27 |
| `bench_js/worker_cost.mjs`, `bench_js/worker_cost.txt` | Synthetic worker CPU estimate for the broker grid |
| `verify_v00_state.*` | Live state during the verification (latest dates, monitoring rows) |
| `verify_v01_broker_profile.*` | `broker_type` and class of named brokers; F05 brokers absent from the profile (none on 2019-06-14 and 2026-10-27) |
| `verify_v02_f05_independent.*` | FL01, FL02, FL03, FL18 from F05 instead of F03/F06; FL08, FL09 via the identity, FL10, FL12; sum of all broker nets |
| `verify_v03_fl16_f05.*` | FL16 from F05 `buy_freq`; the ratio on 2026-10-23; market-wide trades per session |
| `verify_v04_fl15_identity_days.*` | Stock-days whose daily top-3 balance is 0 by construction, by liquidity third |
| `verify_v05_fl13_regular.*` | FL13 all boards, `q19`'s mixed variant and Regular end to end |
| `verify_v06_f03_per_date.*`, `verify_v07_f05_per_date.*` | More cold per-date reads of F03 (4 dates) and F05 (1 date) |
| `verify_v08_fl04_streak.*` | FL04 by another method; \|FL02\| < 1 % count |
| `verify_v09_missing_board_today.*`, `verify_v10_byan_f06.*` | Stocks whose Nego/Tunai flow has no row today; BYAN and CARE stored F06 rows |
| `verify_v11_freq_coverage.*` | Frequency nulls on 4-letter tickers, 12 more dates, every board |
| `verify_v12_price_0917.*`, `verify_v13_calendars.*`, `verify_v14_nego_only_days.*` | Price rows on 2026-09-17/18; broker days vs price bars; Nego-only days and their foreign net |
| `verify_v15_m157_share.*` | Share of Regular rows with foreign + domestic ≠ 0 per year, 2016-2020 |
| `verify_rerun_q11_*`, `verify_rerun_q14_*`, `verify_rerun_q20_*`, `verify_rerun_q22_*` | Verbatim re-runs; identical to the recorded outputs |

### 16.14 Verification

An adversarial check of this section, read-only, on 2026-10-28 between 13:55 and 14:20 UTC. The repository was read at
`main` `8a236eb`. The live data was unchanged since the first reads: every table still ends on 2026-10-27, and the newest
monitoring row is still `51a399f1` SUCCESS (`verify_v00_state.txt`). Every query ran alone and was bounded by literal dates.
No query scanned `IDX_Broker_Summary`, Feature 02 or Feature 05 in full. One attempt hit the 30 s statement timeout (a
correlated subquery, `verify_v08`) and was rewritten. SQL and outputs are in `evidence/flow_proposals/verify_*`.

**What was checked.**
- **Formulas, all 20.** Each formula was checked against its name and against the catalog definitions (`q01`, `q02`) and the
  code: `flow.ts:41-121`, `catalog.ts:54-55` and `brokerAgg.ts:25`.
  - All-board arithmetic: no indicator adds a non-additive stored field across boards. Ratios, shares, HHI, breadth, streaks,
    VWAP, ticket size, z and percentile are rebuilt from summed one-day components (FACT, the SQL of `q10`-`q16`).
  - Each formula matches its name. FL07 equals Backtest `top5` at N = 5: it takes the positive values among the first five
    and the negative values among the last five, with zero-valued brokers in the list.
  - FL05's z matches F06. FL05's percentile now cites the F06 mid-rank rule.
- **Look-ahead.** Every broker and foreign metric uses sessions ≤ t only. FL13 needs the close of the broker as-of date.
  - FL19 is not point-in-time, because its class is current-state.
  - FL20 is not point-in-time, and its published source has no first-seen time (corrected).
- **Data availability.**
  - Every column used exists. F03 has no foreign gross columns (FL03 corrected).
  - Every F05 broker on 2019-06-14 and 2026-10-27 is in `IDX_Broker_Profile` (`verify_v01`).
  - No F05 row has buy and sell both zero, so a missing row means no activity (`q27`).
  - Frequency is non-null for stocks on 18 sampled dates (`q21` and `verify_v11`).
  - The M157 share is 7.25 % of Regular rows in 2016-2020 (`verify_v15`).
  - The current-state class caveat is carried on FL06, FL19 and R8.
- **Live numbers.**
  - **Independent recomputations.** Ten distributions were recomputed with different SQL and, where possible, another
    source: FL01, FL02, FL03 and FL18 from F05 instead of F03 and F06; FL08; FL09 through the identity; FL10; FL12; FL16
    from F05 `buy_freq` instead of F06; FL04 by another method (`verify_v02`, `verify_v03`, `verify_v08`). All ten match
    the recorded min, p10, median, p90, max and samples to the stated rounding.
  - **Identity.** The sum of all broker nets over 10 sessions is 0 for all 832 stocks.
  - **Verbatim re-runs.** Re-running `q11`, `q14`, `q20` and `q22` gave identical outputs.
  - **FL13.** Recomputed with Regular end to end (`verify_v05`).
- **Cost.** The plans' buffer lines were re-read (hit against read, temp written). More cold per-date reads: F03 on 4 dates,
  F05 on 1 date. The synthetic worker benchmark was read: its 8 passes on 1.6 M rows match the stated grid.
- **Interpretation, misuse and references.**
  - Interpretations and misuse warnings were read against the measured behaviour.
  - Reference details (authors, years, journals, volumes) were checked against prior knowledge only. Nothing was fetched.
- **Duplicates.**
  - FL07 and FL09, and FL01 and FL02, are the same quantities in Rp and in %.
  - FL08 is the buy half of FL09.
  - FL11 overlaps FL10, as 16.8 already says.
  - No two indicators share both formula and unit. 16.8 now names the unit-option alternative.

**What was corrected (marked "corrected" in place).**
1. **FL13 board effect.** `q19`'s "Regular" ranked the top buyers on all-board nets. Regular end to end gives 31 (not 34)
   stocks moving > 5 points and 71 (not 70) moving > 1 point, and BYAN at −5.3 %. The Regular distribution of the proposed
   default is added to 16.6 (16.1, 16.3, FL13, D7).
2. **FL03 source.** 16.1 listed FL03 among the Feature 03 series. Feature 03 has no foreign gross buy or sell, so FL03 comes
   from `broker_window`.
3. **F03 per-date cost.** The cost rested on one date (12 ms). Five dates measure 12-26 ms (41-48 blocks). The derived
   figures change: 300 dates take about 4-8 s, not 3.7 s; F06 is about 20-43× slower, not 43× (34× on the same date); the
   total from scratch is 12-85 s (16.1, FL03, FL05, 16.7.2, 16.9, 16.10, D9).
4. **"Cold" labels.** `q12` (2.17 s) and `q13` (3.96 s) were about half served from shared buffers, and `q15` (124 ms) was
   fully warm. Hits and temp written are now in the table, and the temp figures, which mixed read and written, are restated.
5. **Example for the "never add stored windows" rule (16.3).** CARE does not show the failure: its stored rows add up. BYAN
   does: only a Regular row today, −39.72 B against −1,246.00 B on all boards. 73 stocks are affected, 27 by at least
   Rp 1 B.
6. **Calendars and Send to Backtest.** Price bars are missing on Nego-only days (81 stock-days of 15 stocks in 20 sessions),
   and the Backtest's `flowData` skips those broker rows. So `fnet`, `broker` and `top5` do not transfer losslessly for
   those stocks. TRUK, for example, loses +130.5 B of foreign net (16.3, FL01, FL06, FL07, 16.8, 16.10, D12).
7. **FL02 median.** The median is not 0 because "most small stocks have no foreign activity". Only 7 of 832 stocks had no
   foreign trade, and 280 have |FL02| < 1 %.
8. **FL16 median.** 2026-10-27 was not quieter than usual: the market had 1.075× the prior-20 mean of trades. The median below
   1 is structural; it was 0.695 on 2026-10-23.
9. **FL05 window range.** N = 40 or 60 with base 252 needs 292 or 312 ticker sessions. That is more than the 300-session
   series holds, so either cap N at 20 or keep about 340 sessions (FL05, 16.9).
10. **FL20 look-ahead.** `first_seen_at` exists only on the raw table, which the publisher cannot read. The published
    `idx_event_annotation` has `source_fetched_at` (the latest pull) and `ingestion_time`. Column names are now given
    (`value_idr`, `action`, `holder_role`).
11. **FL15.** Days with at most N net buyers and N net sellers have a daily balance of 0 by construction. That is 3.0 % of
    stock-days, and 40 stocks have 5 or more such days, mostly illiquid ones.
12. **Smaller corrections.**
    - FL13 is NULL on a Nego-only evaluation day (4 of 832 stocks).
    - FL07-FL12 were computed on the 828 stocks with a price row.
    - The BBCA breadth and balance example mixed D 20 and D 10, and the correlation windows were unnamed.
    - Evidence for "YP is Foreign-type" now points to `verify_v01` (`q21` shows only the class).
    - The line range `flow.ts:108-119` is now 108-121.
    - The M157 "about 7 %" is confirmed, with the per-year range added.

**What stays uncertain.**
- **Unmeasured live.** FL05's percentile form (only the z form was measured). FL20 (no distribution, no cost). The
  `broker_window` and series file sizes (U4).
- **Predictive value.** No threshold or preset was tested for predictive value. Every number is one cross-section,
  2026-10-27.
- **Frequency coverage** is a sample of 18 dates, not the full history. Tickers that are not 4-letter codes have nulls.
- **Cost figures** depend on the OS cache of a 128 MB buffer pool. The production publisher's round trips were not measured.
  The worker CPU figure is synthetic.
- **Window arithmetic.** FL07's "D + n ≤ 41" depends on how "within n" counts sessions; it may need to be D + n ≤ 40.
- **"Buy intensity".** The user's word is read here as FL08 (decision D4). The user may mean another measure.
- **Stockbit's Bandar Detector formula.** Not checked, as 16.12 says.
- **Broker class.** It may have changed over time. Its history is not stored, so FL19 for past dates cannot be checked.


## DATABASE / FEATURE CHANGES

Approval items 8 (exact code files), 9 (database changes), 10 (Feature 04 changes) and 11 (backfill strategy), plus the records the repository rules require. Labels and evidence notation as in TARGET ARCHITECTURE. Every change below is **PROPOSED**: it is the plan the execution follows. FACT: the user gave the "go" on 2026-10-28 for execution phase by phase on dev (`EXEC.md` EXEC-SCREENER: "Arti gas maksudnya tetap jalankan sesuai fase"), with the decisions of UNKNOWNS / PRODUCT DECISIONS 13.2; each change is claimed only when it is verified live (AGENTS.md).

### 7.1 Exact code files (approval item 8)

Phase: **0** = branch only, no deploy; **1** = dev, under the go of 2026-10-28; **1b** = Send to Backtest; **2** = flow.

FACT (branch commit `8a236eb`, 2026-10-28): Phase 1 work has started on the branch with the sub-app scaffold (`apps/edge-bff/screener/` `package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`, `src/main.ts`, smoke and fixture entry points) and a draft `src/core/contract.ts`; nothing is deployed. The table below is the full plan.

**New files.**

| Path | New / changed | Purpose | Phase |
|---|---|---|---|
| `apps/edge-bff/screener/src/core/contract.ts` | new | Wire types for run, preview, catalog, saved items; imported by the worker and the page | 0 |
| `apps/edge-bff/screener/src/core/validate.ts` | new | Refusals that name the field, the allowed values and the fix | 0 |
| `apps/edge-bff/screener/src/core/registry.ts` | new | Loads and checks the generated `screener-registry.json` | 0 |
| `apps/edge-bff/screener/src/core/metrics.ts` | new | Metric reference → series; the one `series(id, params, output)` path (TARGET ARCHITECTURE §6.7) | 0 |
| `apps/edge-bff/screener/src/core/transforms.ts` | new | Condition arithmetic over `F` outputs (`pct_distance`, `band_position`, `lag`, `change`, `rolling_max/min`, `ma`, `ratio`, `vs_index`) | 0 |
| `apps/edge-bff/screener/src/core/evaluate.ts` | new | VALUE, STATE, EVENT at the evaluation bar, with NA reason codes | 0 |
| `apps/edge-bff/screener/src/core/match.ts` | new | `met`, `need` (via core `entryNeed`), match, the one near rule, counts | 0 |
| `apps/edge-bff/screener/src/core/plan.ts` | new | Planner stages S0-S4 and the pruning rule (§6.10) | 0 |
| `apps/edge-bff/screener/src/core/xsection.ts` | new | Cross-sectional ranks on the fixed population (P7) | 0 |
| `apps/edge-bff/screener/src/core/universe.ts` | new | Universe filters; the same function runs in the page (popover counts) and the worker | 0 |
| `apps/edge-bff/screener/src/core/presets.json` | new | Presets, as data | 0 |
| `apps/edge-bff/screener/src/core/screener-overlay.json` | new | Hand-kept product choices only: shape, allowed tests, search synonyms, labels; plus explicit overrides with evidence, each tested against its probe (today one: I09 `factor > 0`) | 0 |
| `apps/edge-bff/screener/src/core/screener-registry.json` | new (generated) | Base registry + overlay + fields derived at build time by probes on `F` (`first_valid_bar`, `history_class`, unit, `level_comparable`, `price_compare_lag`, `inputs` per source, narrowing, `cost_class`, oracle mapping, caps; TARGET ARCHITECTURE §6.8) | 0 |
| `apps/edge-bff/screener/src/core/screener-metrics.json` | new (checked by the generator) | Non-indicator metric catalog: the 32 fundamental metrics, F1-F8, B1, B4, D1, D4, transforms, patterns, universe attributes, each with params, `requires {file, columns}`, `applies_to`, unit, formula, interpretation, misuse warning, evidence path; the `periods` block (21/63/126/252 sessions, P23 a). Availability and the valid `fn`/`type`/`metric` values are derived from it (§6.12) | 0 |
| `apps/edge-bff/screener/scripts/build-screener-registry.mjs` | new | Generator with `--check`; runs the probes | 0 |
| `apps/edge-bff/screener/src/core/to-backtest.ts` | new | Definition → Backtest cards, with the lossless/lossy classification | 1b |
| `apps/edge-bff/screener/src/core/flowmetrics.ts` | new | Flow metrics, `topNAccumulation` | 2 |
| `apps/edge-bff/screener/tests/core/*.test.ts` | new | Unit, property, parity and drift tests (TEST PLAN) | 0 |
| `apps/edge-bff/screener/{package.json, vite.config.ts, tsconfig.json, index.html}` | new | Vite 7.1.9 + TS 5.9.3 sub-app, `base:'/screener-app/'`, one IIFE classic script, `cssCodeSplit:false`, modes production / smoke / fixture (Backtest precedent) | 1 |
| `apps/edge-bff/screener/src/{main, state, universe-ui, presets-ui, builder, browser, results, preview, dialogs, storage, texts}.ts`, `src/styles/screener.css` | new | Module-by-module port of the prototype markup, CSS and behaviour (`audit/html_ui.md` §6) | 1 |
| `apps/edge-bff/screener/src/api/{types, live, fixture}.ts` | new | `ScreenerApi` interface, live client (`/api/v1/screener/*`), fixture for visual tests only | 1 |
| `apps/edge-bff/screener/tests/{bundle, page, visual}/*` | new | Bundle test (no formula or fixture code in production), page tests, 1:1 visual compare | 1 |
| `apps/screener-worker/Dockerfile` | new | Repository-root context; copies its `src`, `apps/edge-bff/{terminal/src/calc, terminal/src/data/indRegistry.json, backtest/src/core, screener/src/core}`, `apps/backtest-worker/{src/terminal.ts, loader, scripts/build-registry.mjs}` | 1 |
| `apps/screener-worker/{package.json, README.md, CONTRACT.md}` | new | No dependency; start command with `--experimental-strip-types --import ./loader/register.mjs`; the private API contract | 1 |
| `apps/screener-worker/src/{server, config, refresh, snapshot, pool, thread, run, preview, catalog, version, errors, log}.ts` | new | HTTP server and key check; limits from the environment with no defaults; refresh (includes the thin `/state` and `/xsection` client: `TerminalClient.api` is private, `terminal.ts:414` at `010af1e`, and `TerminalClient.publication()`, `terminal.ts:595-603`, returns only `finished_at`, `price_through` and `broker_through`, so the `xsection` index needs its own reader); snapshot build and swap; thread pool; run, preview and catalog handlers; version hashes; errors; JSON logs | 1 |
| `apps/screener-worker/tests/*.test.ts` | new | Refresh integrity, swap, versions, limits, API | 1 |
| `apps/edge-bff/app/screener.py` | new | `routes(app, session, write)`, `ScreenerError`, store over the house `Store`, `guard()`, relay, latest wins per owner | 1 |
| `apps/edge-bff/tests/test_screener.py` | new | Routes, CSRF, limits, relay errors, store owner filter, migration refusal tests | 1 |
| `scripts/screener/check_backtest_untouched.mjs` | new | Tripwire: `engineVersion()` and `REGISTRY_VERSION` equal those of `origin/main`; the listed paths have no diff | 0 |
| `scripts/screener/parity_f04.py` | new | Snapshot vs Feature 04 (and Feature 01) on all equity tickers at a common date | 0 |
| `scripts/screener/bench.mts` | new | The Phase 17 benchmark driver | 1 |
| `verification/screener/{AUDIT.md, F04_PARITY.md, BENCHMARK.md, E2E.md}` | new | This report; pinned parity record; benchmark results; E2E record | 0 / 1 |
| `database/migrations/2026MMDD_NNN_edge_bff_screener.sql` | new | Saved items and watchlist tables (§7.2) | 1 (P12) |
| `database/migrations/2026MMDD_NNN_terminal_publisher_feature_reader.sql` | new | Read group on F06 for the publisher (§7.2) | 2 |

**Changed files.**

| Path | New / changed | Purpose | Phase |
|---|---|---|---|
| `apps/terminal-publisher/publisher.py` | changed | xsection writer (`price`, `actions`; Phase 2 `flow_f06`, `broker_window`; the existing reference file `ref/tickers.json.gz` is reused, not copied), index in `state.json`, carry-forward of the index in other modes, pruning of unreferenced xsection objects | 1 / 2 |
| `apps/terminal-publisher/tests/test_publisher.py` | changed | Each ticker's slice equals its pack; index written before `state.json`; carry-forward; pruning keeps the previous index's objects; completeness gate (Phase 2) | 1 / 2 |
| `apps/terminal-api/app/bucket.py` | changed | `xsection` joins `STATE_FIELDS` (line 8), so the existing `GET /state` (`main.py:297-305`, live since terminal-api `689dc465`) answers the index; `Bucket` gains the index lookup `POST /xsection` uses | 1 |
| `apps/terminal-api/app/main.py` | changed | `POST /xsection` only, proxy-key callers only, one audit row under `quota.REF` (no terminal-schema migration) | 1 |
| `apps/terminal-api/tests/test_api.py` | changed | `/xsection`: proxy key required (a direct subscriber refused), quota and one audit row; `/state` returns `xsection` when `state.json` holds it; the existing `/state` tests kept, `test_bucket_state_keeps_the_last_read_publication` gaining the new field | 1 |
| `apps/edge-bff/app/main.py` | changed | `/screener` index route; `/screener-app/` page and asset routes; `SCREENER_CSP` (`connect-src 'self'`); mount `screener.routes` | 1 |
| `apps/edge-bff/app/config.py` | changed | `SCREENER_WORKER_URL` / `SCREENER_WORKER_KEY` pair (key ≥ 32 characters, private host outside `local`, `config.py:75-98` pattern) | 1 |
| `apps/edge-bff/static/index.html` | changed | Nav entry, `ScreenerPage` frame, `go()` allow-list and path map, `App` switch, `postMessage` navigation listener (§6.15) | 1 / 1b |
| `apps/edge-bff/static/edge-labels.js` | changed | `screener: {nav, frameTitle}` (AGENTS.md: shell wording lives here) | 1 |
| `apps/edge-bff/Dockerfile`, `apps/edge-bff/.dockerignore` | changed | A `screener` Node stage (copies `terminal/src` and `backtest/src/core` beside it, as the backtest stage copies `terminal/src`, so `tsc` can typecheck screener core); ignore `screener/node_modules`, `screener/tests`, `screener/dist*`, `static/screener-app` | 1 |
| `apps/edge-bff/tests/test_backtest.py` | changed | Pinned tab list `['Monitor','Terminal','Backtest']` (about line 1993) and image COPY list (about lines 1497-1524) gain the Screener (`audit/edge_conventions.md` §1.7-1.8) | 1 |
| `apps/edge-bff/tests/conftest.py` | changed | Apply the new migration; add the tables to the truncate list | 1 |
| `scripts/provision_edge_bff_login.py` | changed | Reach and grant sets for the two new tables; otherwise it refuses ("EDGE has unexpected reachable relations", line 36) | 1 |
| `apps/edge-bff/README.md` | changed | "Screener tab" and "Persistence and ownership" | 1 |
| `apps/edge-bff/backtest/src/app.ts` | changed | `boot()` (`app.ts:37-62` at `010af1e`) reads and deletes the one-shot import key at its start, before the first `load()`; the import is applied when the catalog is known, in `boot()` within `QUICK_MS` or in `catalogArrived()` (`app.ts:67-85`), and counts as an edit (TARGET ARCHITECTURE §6.15). Outside `src/core`, so `engine_version` is unchanged | 1b |
| `apps/edge-bff/backtest/src/import.ts` | new | Handoff → cards via `legacyCard`, registry defaults, `withinLimit`, core validation; toast with what was left out; per-ticker data-version note | 1b |
| `apps/edge-bff/backtest/tests/import.test.ts` | new | Import validation, left-out toast, version note | 1b |
| `BACKTEST_END_TO_END.md` | changed | Read in full first (AGENTS.md: Phase 1 changes publisher files and a terminal-api route the Backtest reads). §4 (publisher: the xsection writer and index), §5 (storage layout: `v1/xsection/`), §6 (route table: `/state` answers `xsection`; it is listed as "worker only", line 286, while the code admits any subscriber; `POST /xsection`), §11 (caches) | 1 |
| `apps/edge-bff/backtest/CONTRACT.md` | changed | [D-L3] (lines 77-83) gains the `xsection` field of `/state` | 1 |
| `BACKTEST_END_TO_END.md`, `apps/edge-bff/backtest/CONTRACT.md` | changed | The import (CONTRACT §10 Page; end-to-end §10) | 1b |
| `verification/terminal_api/INTEGRITY.md` | changed | `state.json` gains `xsection`; the bucket listing gains the `v1/xsection/` objects | 1 |
| `UPDATE_TABLE.md` | changed | A step after a manual F05/F06 refresh: the rack's flow files stay as published until the next publisher run, so republish them (or note the lag) | 2 |
| `scripts/terminal_indicator_spec.py`, `verification/terminal_api/INDICATOR_SPEC.md` | changed | A `--json` mode the screener generator reads; the derived oracle rows (I25, I28, I29, I31, I32, Feature 01) added to the `feature04` column. The applied migration `20261025_102` it also generates does not read that column; `--check` proves it unchanged | 0 |
| `.github/workflows/screener-checks.yml` | new, optional (CHANGES AWAITING APPROVAL A9) | On PRs touching the screener-worker watch paths: tripwire, backtest-worker `npm test` and `npm run registry:check`, Terminal calc tests, screener core tests | 1 |
| `scripts/provision_terminal_logins.py` | changed | `terminal_publisher_login` groups gain `terminal_publisher_feature_reader`; its reach gains F06 (and F04 if the reconciliation file is approved) | 2 |
| `.railway/railway.ts` | changed | After `railway config pull --force` (the live edge-bff variables enter first): `screener-worker` service; edge-bff `SCREENER_*` variables; applied through a pinned plan (TARGET ARCHITECTURE §6.17) | 1 |
| `PROJECT_CONTEXT.md` | changed | `screener-worker` service ID once created | 1 |
| `PLAN.md` / `EXEC.md` | changed | Done: the approval words and P1-P23 under PLAN.md SCREENER (R34), then the decisions and the go, with the item moved to `EXEC.md` EXEC-SCREENER (commit `88d3344`); the execution record continues there (AGENTS.md "Plans") | 0 / 1 |
| `FUTURE_PLAN.md` | changed | Done: E1-E5 (CHANGES AWAITING APPROVAL 14.6) as proposals (commit `514057e`); the links from ERRORS D22, D23 and D26-D28 are still to be added | 0 |
| `ERRORS_AND_SOLUTIONS.md`, `RAILWAY_CHANGELOG.md`, `DATABASE_CHANGELOG.md`, `database/migrations/APPLIED.sha256` | changed | §7.5 | 0-2 |

**Must not change (tripwire, I3 and I4).** `apps/edge-bff/terminal/src/calc/indicators.ts`, `apps/edge-bff/terminal/src/data/indRegistry.json`, `apps/edge-bff/backtest/src/core/**` (including `backtest-registry.json` and `flow.ts`), `apps/backtest-worker/**`, `features/feature04/**`, `apps/feature-04-worker/**`, the Feature 04 tables, `apps/stockbit-updater/**`.

### 7.2 Database changes (approval item 9)

Two forward migrations, one per phase. No public table, column, index, Feature or routine is created or changed.

**Migration 1 (Phase 1, P12 a, decided 2026-10-28): `edge_bff` saved items and watchlist.** House style of the five existing `edge_bff` migrations (`audit/edge_conventions.md` §1.6): `BEGIN; SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='1min'`; a `$preflight$` block refusing a missing schema or role or an existing table; `COMMENT ON` for tables and non-obvious columns; `REVOKE ALL ... FROM PUBLIC`; exact grants; a `$verify$` block that checks each privilege one call at a time, checks nothing more is held (TRUNCATE, REFERENCES, TRIGGER) and that PUBLIC holds nothing; the rollback body as a comment.

| Table | Columns and constraints | Grants to `edge_bff_runtime` |
|---|---|---|
| `edge_bff.screener_items` | `item_id text PK CHECK (item_id ~ '^scr_[0-9a-f]{32}$')`; `owner_key text NOT NULL`; `kind text NOT NULL CHECK (kind IN ('screen','metric'))`; `name text NOT NULL CHECK (length 1-120 and name = btrim(name))`; `definition jsonb NOT NULL CHECK (object, octet_length ≤ 65,536)`; `schema_version integer NOT NULL ≥ 1`; `registry_version`, `screener_registry_version`, `definition_hash text NOT NULL` (length-checked); `revision bigint NOT NULL DEFAULT 1 CHECK (> 0)`; `created_at`, `updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP`; `UNIQUE (owner_key, kind, name)`; index `(owner_key, kind, updated_at DESC)` | SELECT, INSERT, UPDATE, DELETE |
| `edge_bff.watchlist_items` | `owner_key text NOT NULL`; `ticker text NOT NULL CHECK (ticker ~ '^[A-Z0-9]{1,12}$')` (terminal-api's ticker rule); `added_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP`; `PRIMARY KEY (owner_key, ticker)` | SELECT, INSERT, DELETE |

Rollback (comment in the file): `DROP TABLE edge_bff.watchlist_items; DROP TABLE edge_bff.screener_items;`. A draft exists at `evidence/edge_conventions/proposed_migration_screener_DRAFT.sql` (not applied, not syntax-checked against a server); it predates the `kind` column and must be updated.

**Migration 2 (Phase 2): publisher read group.**

| Object | Change |
|---|---|
| Role `terminal_publisher_feature_reader` | `CREATE ROLE ... NOLOGIN` (precedent: roles created by `20261025_100_create_terminal_schema.sql`) |
| Grant | `GRANT SELECT ON public."Feature_06_Foreign_Domestic" TO terminal_publisher_feature_reader`; optionally `public."Feature_04_Technical_Indicator"` for the reconciliation file (§7.3). FLOW INDICATOR PROPOSALS 16.10 proposes SELECT on `public."Feature_03_Stock_Broker_Daily"` instead of, or beside, Feature 06 for the long all-board series; the table is chosen with the flow indicators (its decision D9) before this migration is written |
| Membership | `GRANT terminal_publisher_feature_reader TO terminal_publisher_login` only |
| `$verify$` | `terminal_publisher_login` can SELECT F06 (and F04 only if granted); `terminal_api_login` and `terminal_market_reader` cannot; the new group holds SELECT only (no INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER); no other role's privileges change |
| Rollback (comment) | `REVOKE terminal_publisher_feature_reader FROM terminal_publisher_login; REVOKE SELECT ON ... FROM terminal_publisher_feature_reader; DROP ROLE terminal_publisher_feature_reader;` |

Why a new group (FACT, live L1-L3, TARGET ARCHITECTURE live checks): `terminal_api_login` and `terminal_publisher_login` are both members of `terminal_market_reader`; the publisher login cannot SELECT F06 or F04 today; `edge_bff_runtime` reads none of the 87 tables and views of schema `public`. `scripts/provision_terminal_logins.py:15-31` rolls back unless each login reaches exactly its listed relations, so a grant to the shared group would widen the public terminal-api's reach.

**Catalogs and schema documentation.**
- `Table_Catalog`, `Column_Catalog`, `Feature_Catalog`, `Feature_Relationship_Catalog`, `Tool_Catalog`: no rows. FACT: `Table_Catalog` covers only schema `public` (84 rows, live L4), and the `edge_bff` backtest tables (migration `20261026_005`) set the precedent of no rows. No public table, column, Feature or routine changes.
- `DATABASE_SCHEMA.md`: unchanged in content. FACT: it is generated from schema `public` by the nightly workflow (`.github/workflows/database-schema-docs.yml`) and records no grants (grep: 0 hits). `edge_bff` is documented in `apps/edge-bff/README.md`, the migrations and `DATABASE_CHANGELOG.md`.
- Indexes: none. The publisher's new statements use existing indexes (Price seq scan; F05 `trade_date_idx`; F06 `(trade_date, market_board)` with literal bounds). AGENTS.md "Performance" asks for measured plan evidence first, and the run also feeds the Terminal and the Backtest on a 128 MB buffer pool shared with the AI (U6 is an INFERENCE of 10-40 s). So the exact Phase 1 price statement and the Phase 2 per-date F06 and F05 statements get a bounded read-only `EXPLAIN (ANALYZE, BUFFERS)` with literal bounds through pgweb before their phase's go, recorded in `DATABASE_CHANGELOG.md` (NEXT ACTION 15.1); the first dev run confirms them. FACT already measured: the calendar-CTE form planned a seq scan of F06 taking 18.6 s, and per-date multi-date reads took 3-8 s (`audit/flow.md` §5).
- `scripts/onboarding/measure_indexes.py` and `NEW_TABLE_ONBOARDING_PLAN.md`: not triggered; nothing is exposed to the AI.

**Not proposed.** A persisted screener table (a variant of the brief's Options B and C, §7.3), a Feature_07 flow table, any change to Feature 04 tables, `VACUUM FULL` of Feature 04 (its 4.36 rows/page density is recorded separately, ERRORS D28).

### 7.3 Feature 04 changes (approval item 10)

**None (DECIDED, P2 a, 2026-10-28).** No column, VERSION, checkpoint, worker, engine or migration change; the screener does not read Feature 04 at runtime.

**The brief's options, as the brief defines them** (brief, Phase 3):

| Brief option | Meaning here | Verdict | Evidence |
|---|---|---|---|
| A. Extend Feature 04 | Add the 42 indicators it does not serve to `engine.py` and `incremental.py`, bump VERSION, rewrite about 1.39 M rows | Rejected | `audit/verify_feature04.json` F04-14, F04-18, F04-19, F04-20; bullets below |
| B. Feature 04 focused, plus a dedicated snapshot or table; Feature 04 read where appropriate | Read the 9 indicators Feature 04 fully serves at runtime; the rest from a snapshot | Rejected as a runtime source (P2 b): a second time base (Feature 04 finishes at 10:09 UTC, the rack at about 13:03 UTC), a new grant, coupling to `REPAIR_REQUIRED`, and no precision gain (max relative difference 1.16e-15) | TARGET ARCHITECTURE §6.6; `audit/benchmark.md` §2f |
| C. Mixed model: Feature 04 keeps broadly reusable features, a smaller Screener snapshot holds the defaults, custom parameters are dynamic | Feature 04 unchanged and used as the parity oracle; the Screener snapshot held in memory per publication, not in a table; custom parameters dynamic | **Chosen, with one restriction** (P2 a): Feature 04 is not read at runtime | TARGET ARCHITECTURE §6.6, §6.7 |
| Variant of B and C: a persisted screener table | Store the snapshot in PostgreSQL | Rejected: a writer credential, a migration, catalogs and an onboarding to store values recomputable in 8-10 s from the rack | below |

**Phase 5 answers** (brief, Phase 5, items 1-5):
1. *Available at default today:* Feature 04 fully serves 9 indicators (I01 SMA 20, I06 MACD, I13 RSI 14, I27 Bollinger, I30 ATR 14 stored; I28 %B, I29 bandwidth, I31 NATR and I32 stddev derived exactly) and 2 partly (I07: ADX only; I25: PPO line only); Feature 01 serves 2 (I35 `volume_avg_20d`, I37 `volume_ratio_20d`), and I17 at lengths 5, 20 and 60 (FACT, `audit/verify_feature04.json` F04-17; table below).
2. *Missing:* the other 40 indicators at default, plus I07's +DI and −DI, and I25's signal and histogram. Feature 04's `ema_*` columns are not at the registry default (EMA 20).
3. *Belong naturally in Feature 04:* none now. INFERENCE: if Feature 04 is extended later for AI use, EMA 20, SMA 150 and 200, +DI and −DI, and the PPO signal are the natural candidates; that is its own decision, outside this work.
4. *Elsewhere:* all 53 defaults (76 outputs) in the Screener's in-memory snapshot, recomputed by `F` per publication (TARGET ARCHITECTURE §6.7).
5. *Never precomputed:* custom parameter sets (computed on demand, cached in the series LRU); raw cumulative levels are not offered at all (TARGET ARCHITECTURE §6.7).

**Why not extend it (Option A, rejected).** FACT (`audit/feature04.md` §11; `audit/verify_feature04.json` F04-14, F04-18, F04-19, F04-20):
- every indicator implemented twice: the full TA-Lib engine (`engine.py`) and streaming checkpoint state (`incremental.py`);
- a VERSION or `STATE_VERSION` bump invalidates all 6,076 checkpoints, so without a re-bootstrap every next price change ends `REPAIR_REQUIRED`;
- a rewrite of about 1.39 M rows onto a heap at 4.36 rows/page (about 4× the density of its `_INDEX` clone);
- the `_INDEX` table and its catalogs (57 Feature_Catalog, 57 AI_calculation_catalog, 57 AI_column_catalog rows), the stockbit-updater engine copy (`apps/stockbit-updater/deploy.sh:13`) and three more writer scripts (`scripts/repair_fixed_income_dates.py`, `scripts/ihsg_price_release_job.py`, `scripts/initialize_index_feature_sample.py`) must change in step;
- `backfill.py` and `bootstrap_states.py` abort at IHSG today (INFERENCE from code, not executed);
- and it would still serve only default parameters, from a different time base.

**Why not a persisted screener table (a B/C variant, rejected).** A writer credential, a migration, catalogs and an onboarding to store values recomputable in 8-10 s from the rack.

**Feature 04 as parity oracle** (FACT, `audit/verify_feature04.json` F04-17; `audit/verify_matrix_a.json` I17; `audit/verify_matrix_b.json` I33). Values are equal only when computed from each ticker's first price row.

| Indicator | Oracle |
|---|---|
| I01 SMA | `sma_20`, `sma_50` |
| I02 EMA | `ema_12`, `ema_26`, `ema_50`, `ema_200` |
| I06 MACD | `macd`, `macd_signal`, `macd_histogram` |
| I07 ADX | `adx_14` (ADX output only) |
| I13 RSI | `rsi_14` |
| I27 Bollinger | `bb_upper_20`, `bb_middle_20`, `bb_lower_20` |
| I30 ATR | `atr_14` |
| I28, I29, I31, I32, I25 | Derived: %B, bandwidth, NATR = 100·`atr_14`/close, stddev = (upper − basis)/2, PPO line = 100·(`ema_12` − `ema_26`)/`ema_26`; denominators wrapped in `NULLIF(..., 0)` |
| I35, I37 | Feature 01 `volume_avg_20d`, `volume_ratio_20d` |
| I17 | Feature 01 `return_{5,20,60}d_pct`, exact |
| I33 | No oracle: Feature 01 volatility is a different formula (sample stdev of simple returns), median 2.8% and max 23% apart |

IHSG values are in `Feature_04_Technical_Indicator_INDEX`.

**Verification.** Snapshot vs Feature 04 on all equity tickers at a common date, for the registry-default columns (`sma_20`, the 3 MACD columns, `rsi_14`, the 3 Bollinger columns, `atr_14`, `adx_14`) plus the 5 derivations; the configurations Feature 04 stores at other parameters (`sma_50`, `ema_12`, `ema_26`, `ema_50`, `ema_200`) are reached through the dynamic path and compared the same way (TEST PLAN 10b.2); relative difference ≤ 1e-12 and identical nulls (FACT today: max 1.16e-15 on 828 rows, `audit/benchmark.md` §2f; 1.25e-15 on 114,544 rows of 844 tickers, `evidence/verify_matrix_a/v_market.txt`). A perturbed fixture must fail. Pinned in `verification/screener/F04_PARITY.md` with `registry_version` and the Feature 04 VERSION string.

**Optional, Phase 2:** an `f04` xsection file with the latest equity cross-section (about 828 rows; 2-84 ms to read, `audit/benchmark.md` §3) for continuous reconciliation. The worker logs mismatch counts and never alters results. Needs the optional F04 grant in migration 2.

**Feature 04 items found by the audit, outside screener scope** (each needs its own approval): the planned 2026-09-17/18 price refill would put about 840 equity tickers into `REPAIR_REQUIRED` (`EXEC.md` F3; `audit/verify_feature04.json` additional findings); `backfill.py` and `bootstrap_states.py` abort at IHSG; heap density 4.36 rows/page; documentation drift (`_INDEX` Table_Catalog `update_rule`, `INDICATOR_ALIGNMENT.md` "24" candles vs 25). They are recorded as ERRORS D26, D27, D28, C09 and C11 (2026-10-28, §7.5) and not fixed by this work.

### 7.4 Backfill strategy (approval item 11)

**None.** FACT: price history is published from 2018-01-02 and broker history exists from 2016-01-04 (`audit/reuse.md` §1.3; `audit/flow.md` §1). PROPOSED:
- The first publication after the publisher deploy builds every xsection file from existing data: `price` (full history, one statement), `actions`; in Phase 2 `flow_f06` (130 sessions) and `broker_window` (41 complete sessions). Nothing is stored in PostgreSQL.
- The worker builds its snapshot from those files at start and at every new `finished_at`. A restart re-reads the current files (disk cache first).
- Feature 04: no backfill (no change).
- Saved items: no server data to migrate. INFERENCE: prototype data saved on another origin cannot be read by EDGE (`audit/edge_conventions.md` §3.1). With P12 (a) decided, no local adapter exists, so no import is needed.
- A manual publisher run before the first scheduled one follows the documented procedure (clear the cron schedule, `railway up` a new deployment, restore the schedule; `publisher.py:17-21`, ERRORS M229), outside the M250 windows.

**Rollback.** Revert the publisher and terminal-api deployments; the xsection objects become unreferenced and are pruned (or deleted by key); the worker's `/ready` fails and edge-bff answers `SCREENER_NOT_READY`. No database data is involved.

### 7.5 Records the repository rules require

| Record | Content | When |
|---|---|---|
| `ERRORS_AND_SOLUTIONS.md`, new entries | **Done, recorded 2026-10-28** (commits `270dde5`, `ad7ba34`), one entry per defect, each with symptom, verified or suspected root cause (with the check that settles it), class, solution, status and lesson (Part D): M255 Donchian `price > upper` is never true in the Backtest's indicator condition; M256 registry I37 shows `include_current_bar = false` while RVOL includes the current bar; M257 the registry accepts Supertrend `factor` 0 (direction flips on about half the bars); M258 `annualization_periods` typed `number` but floored silently (`indicators.ts:239, 249`); D24 stockbit-updater round `3323340d` FAILED, "Object of type date is not JSON serializable"; D25 `Monitoring_Stockbit_Update` row `e3331473` left `RUNNING`; D26 the planned 2026-09-17/18 price refill (EXEC F3) would put about 840 tickers in `REPAIR_REQUIRED`; D27 Feature 04 `backfill.py` and `bootstrap_states.py` abort at IHSG; D28 Feature 04 heap density 4.36 rows/page (root cause suspected, not dead tuples); C09 `_INDEX` `Table_Catalog.update_rule` and `Feature_Catalog.refresh_trigger` say no automatic update; C10 `AI_formula_reference` CALC_225 (two-pass stdev) and CALC_041 (bar-0 true range) differ from the implementations; C11 `INDICATOR_ALIGNMENT.md` says 24 candlestick patterns, Feature 04 has 25; D29 37 F06 Regular tickers outside `IDX_Stock_Universe` (ETFs plus AKKU, CRAB, GTBO, TRUE, UNSP); M259 `POST /api/v1/dev/manual/steps/{step_id}` has no CSRF check; M260 the Terminal gateway relays terminal-api JSON without `public_data` (`apps/edge-bff/app/main.py:384-388`); M261 edge-bff 401/403 return `{"detail": ...}` outside the error shape; R41 `.railway/railway.ts` lacks edge-bff `EDGE_TERMINAL_URL` and `TERMINAL_PROXY_KEY`; R42 `railway.ts` gives backtest-worker builder `RAILPACK` while its deployments built with `DOCKERFILE`; D30 DIRE funds XCID, XCIS, XSPI typed `stock/common` in `IDX_Stock_Universe` (Part A A1.4 gained a sub-bullet). All OPEN; M255-M258 carry the Screener's TEMPORARY mitigation, paired with the registry release (P6), and M261 the TEMPORARY exception of API CONTRACT §8.1; D26 is not triggered while EXEC F3 stays deferred. Corrections found while recording: the floor is at `indicators.ts:249`, the CSRF test line at `test_manual_routes.py:34`, BBRI's refill suffix 29 rows. Also recorded: R43 (FIXED), a git detached-HEAD push slip in this session | Done in Phase 0 (Part D: the task that finds a defect records it) |
| `ERRORS_AND_SOLUTIONS.md`, existing entries | **Done, 2026-10-28:** D22 updated in place (FORU added as a second instance, the derived count of 8 price-affecting actions between `ADJUSTED_HISTORY_BOUNDARY` and 2026-10-27, and the Screener's TEMPORARY rule); D23 corrected to "844 of 844 rows are consistent with a swap; 841 differ, the other 3 are `Undefined` in both columns". Still to do: D22's Solution names the per-cell NA rule, which P4.1 (A) replaced by values with remarks, so it is updated when Phase 1 lands; M250: note the xsection family as its first content-addressed application | Phase 0 (done); the D22 wording and the M250 note when Phase 1 lands |
| `DATABASE_CHANGELOG.md` | Each migration with the live read-back of tables, grants and `$verify$` result | Phase 1, Phase 2 |
| `database/migrations/APPLIED.sha256` | One line per applied migration (`apps/market-ai-orc/tests/test_migrations_frozen.py`) | After each apply |
| `RAILWAY_CHANGELOG.md`, `.railway/railway.ts` | New service, variables (names only), each deployment ID at SUCCESS; then `railway config pull --force` and `railway config plan` | Each deploy |
| `PLAN.md` / `EXEC.md` | **Done, 2026-10-28:** the approval words and the open decisions P1-P23 under PLAN.md SCREENER (R34), then the decisions and the go, with the item moved to `EXEC.md` EXEC-SCREENER (commit `88d3344`); removal when done | Phase 0 and the go (done); at completion |
| `FUTURE_PLAN.md` | **Done, 2026-10-28:** E1-E5 as proposals (commit `514057e`). Still open: ERRORS D22, D23 and D26-D28 do not yet link to them | Phase 0 (done); the links with the next ERRORS edit |
| `BACKTEST_END_TO_END.md`, `CONTRACT.md`, `verification/terminal_api/INTEGRITY.md`, `UPDATE_TABLE.md` | As listed in §7.1 | Phase 1 (end-to-end §4/§5/§6/§11, [D-L3], INTEGRITY); Phase 1b (§10 Page); Phase 2 (UPDATE_TABLE) |
| `PROJECT_CONTEXT.md`, `apps/edge-bff/README.md`, `apps/screener-worker/README.md`, `CONTRACT.md` files | Service IDs, tab, persistence, private API | Phase 1 / 1b |
| `AI_TOOLS.md`, `AI_MODELS.md`, `AI_ROUTER.md`, `prompts/SYSTEM_PROMPT_HISTORY.md` | Not touched: no model tool, model call, router or prompt changes | — |


## API CONTRACT

Approval item 12. Everything here is **PROPOSED** unless labelled; the conventions it follows are **FACT** from `apps/edge-bff/app/backtest.py` and `apps/edge-bff/app/main.py` (`audit/reuse.md` §5; `audit/edge_conventions.md` §1.2-1.5). Labels and evidence notation as in TARGET ARCHITECTURE.

### 8.1 Conventions inherited from the Backtest API (FACT)

| Convention | Source | Screener use |
|---|---|---|
| Session cookie on every route (`Depends(session)`, a DB lookup per request, through the pool of `store.py` since EXEC-BACKTEST-LOAD) | `main.py:247-252` (main `010af1e`) | Same |
| `Depends(write)` on every POST, PUT, DELETE: exact `Origin`, `X-CSRF-Token` | `main.py:224-227, 254-257` | Same, including `run`, `preview`, `validate`, `counts`; a test walks `app.routes` and fails on any screener write route without `write` (the class of ERRORS M259) |
| Body ≤ 131,072 bytes, else 413 `REQUEST_TOO_LARGE` | `main.py:228-234` | Same |
| `loads()` refuses NaN, Infinity, numbers beyond a double, lone surrogates, over-deep nesting → 422 `INVALID_INPUT` | `backtest.py:94-105` | Shared helper |
| Error shape `{"error": {"code", "field?", "message?", "details?"}}` | `apps/edge-bff/backtest/CONTRACT.md` §11 | Same. **TEMPORARY exception:** 401/403 from the auth dependencies are `{"detail": ...}` (`main.py:251, 256`), which the Backtest client already maps. It is recorded as a defect (ERRORS M261, 2026-10-28) with its general fix, one exception handler that maps `HTTPException` to the error shape for every route, with the Backtest `live.ts` mapping adjusted; until that fix the screener client maps `detail` the same way |
| Relay `ask()`: 2xx → JSON; worker 4xx → its error after `error_of` + `public_data`; worker 504 → 504; anything else → 503 `*_UNAVAILABLE`; awaited on the event loop | `backtest.py:949-968` | Same, `SCREENER_UNAVAILABLE` |
| Read timeout = worker deadline + `CONTROL_TIMEOUT` (30 s) | `backtest.py:957` | Same rule (the draft design proposed +10 s; the house rule is kept) |
| `unless_gone` cancels the worker call when the browser leaves | `backtest.py:971-1000` | Same, for `run` and `preview` |
| Latest wins per owner with `client_order {page, seq}`; a replaced call answers 409 | `backtest.py:270-280, 1002-1033` | 409 `SCREEN_REPLACED` / `PREVIEW_REPLACED`, keyed by (owner, page) rather than by owner alone, so two tabs or two people on one login do not cancel each other (MULTI-USER SCALE AND COST 6d.6) |
| `guard()`: 503 `*_DISABLED` without a worker URL; 503 `*_NOT_READY` while the tables are missing | `backtest.py:942-947, 406-424` | `SCREENER_DISABLED`, `SCREENER_NOT_READY` |
| Default response headers `Cache-Control: no-store`, `nosniff` | `main.py:235-245` | Kept |

### 8.2 Routes (edge-bff, under `/api/v1/screener/`)

Literal routes are declared before parameterised ones (as `/api/v1/backtests/catalog` precedes `/{request_id}`, `backtest.py:1056, 1120`).

| Method and path | Auth | Purpose | Worker route |
|---|---|---|---|
| `GET catalog` | session | Versions, data status, limits, indicator registry subset, flow / universe / fundamental items with availability and reason, groupings with counts, presets with availability and match/near counts | `GET /v1/catalog` |
| `GET universe` | session | Per-ticker attributes for popovers and the "In universe X of N" count | `GET /v1/universe` |
| `POST run` | write | Run one screen | `POST /v1/run` |
| `POST preview` | write | One ticker: bars, overlays, markers, cells, status | `POST /v1/preview` |
| `POST validate` | write | Validate a definition (used by save and Send to Backtest) | `POST /v1/validate` |
| `POST counts` | write | Match and near counts of up to 50 saved definitions | `POST /v1/counts` |
| `GET items?kind=screen\|metric` | session | List saved items | — (edge-bff store) |
| `PUT items/{item_id}` | write | Create or replace (with `revision`) | `/v1/validate` first |
| `DELETE items/{item_id}` | write | Delete | — |
| `GET watchlist` | session | List tickers | — |
| `PUT watchlist/{ticker}` | write | Add (idempotent) | — |
| `DELETE watchlist/{ticker}` | write | Remove (idempotent) | — |

### 8.3 Shared blocks

**`versions`** (every worker answer):

| Field | Type | Meaning |
|---|---|---|
| `screener_engine` | string (16 hex) | Content hash of screener core, worker `src`, imported core and calc files, Node major |
| `registry` | string (16 hex) | `registry_version` of `backtest-registry.json`, passed through |
| `screener_registry` | string (16 hex) | sha256(base registry + overlay)[:16] |
| `price_data` | string | `dataVersion` over (ticker, `price`, pack sha256) of every ticker |
| `flow_data` | string or null | Same over the flow files; null before Phase 2 |
| `definition_hash` | string (64 hex), run and counts only | sha256 of `canonicalJson` of the definition with parameters resolved and labels removed |

**`data`** (every worker answer):

| Field | Type | Meaning |
|---|---|---|
| `evaluation_date` | ISO date | E = `price_through` |
| `price_through` | ISO date | From `state.json` |
| `flow_through` | ISO date or null | Last complete flow date (Phase 2) |
| `broker_behind_sessions` | integer or null | From `state.json` |
| `published_at` | ISO timestamp | `state.json` `finished_at` |
| `refresh` | `ready` \| `failed_keeping_previous` | The publication's outcome (catalog only), equal on every worker replica so the catalog bytes and their `ETag` are too; the transient `refreshing` state and the snapshot age are reported on `/health` (MULTI-USER SCALE AND COST 6d.4 rule 4) |

### 8.4 `GET catalog` and `GET universe`

**Catalog body.**

| Field | Content |
|---|---|
| `versions`, `data` | 8.3 |
| `limits[]` | Every limit of 8.9 as `{name, value, unit, rule, example_ok, example_refused}`, generated from the value (for `max_conditions` 20: `rule` "at most 20 enabled conditions", `example_ok` a screen with 20, `example_refused` one with 21), so the page shows the rule, how to pass it and one right and one wrong example before the user meets it (AGENTS.md "Gates and evidence") |
| `indicators[]` | Per registry id: `id`, `key`, `name`, `category`, `synonyms`, `formula_version`, `params[{key, type, default, min, max (derived cap), exclusive_min, integer, options, step}]` (`not_accepted` removed), `outputs[{key, shape, tests, unit, level_comparable, price_compare_lag, inputs_by_source}]`, `history_class`, `cost_class`, `overlay` (TARGET ARCHITECTURE §6.8) |
| `metrics[]` | Transforms, patterns, cross-section, flow and universe items from `screener-metrics.json` (TARGET ARCHITECTURE §6.12): `id`, `group`, `params`, `tests`, `unit`, `formula`, `interpretation`, `misuse`, `availability` (`AVAILABLE` \| `REQUIRES_DATA` \| `REQUIRES_DECISION` \| `NOT_APPLICABLE`, derived from the files and columns indexed in `state.json`), `reason`, `applies_to` |
| `fundamentals[]` | The 32 prototype metrics from the same file, each with `availability` and `reason` (all unavailable today except dividends from Phase 2) |
| `periods` | The session counts of 1M, 3M, 6M and 1Y (P23), from the same file |
| `groupings` | `[{key, values:[{value, tickers}], unclassified}]` per classification column, built by the Backtest's `groupingsOf` (`apps/backtest-worker/src/catalog.ts:20-31`) from the reference file `ref/tickers.json.gz`: stocks without a classification are counted in `unclassified`, never as a value (`terminal.ts:156`) |
| `presets[]` | `id`, `category`, `name`, `why`, `definition`, `availability`, `reason`, `match_count`, `near_count` at `price_data` |

**Universe body:** `{versions, data, rows: [{ticker, name, sector, industry, last, chg_1d_pct, adv20_idr, first_bar, last_bar, bars, stale, remarks: [{code:'STALE', last_bar_date} | {code:'PRICE_BREAK', action, ex_date, ratio_old, ratio_new, close_ratio}]}]}`. Every listed stock is in it, hidden ones included, so the chips can count what they hide (P4). About 845 rows, about 20 KB gzip (INFERENCE). The page applies `universe.ts` locally for popover counts; the worker applies the same function in stage S0.

**Caching.** edge-bff keeps the last catalog and universe in memory keyed by (`price_data`, `screener_registry`). At most every 60 s it asks the worker's `/health` for its current versions and refetches only when they changed; this replaces a 60 s time-to-live rebuild, the class of problem EXEC-BACKTEST-LOAD fixed for the Backtest by keeping its catalog per publication (`EXEC.md:8444-8462`; `apps/edge-bff/backtest/CONTRACT.md:77-83`, [D-L3] replaced). edge-bff also drops its cached catalog and universe as soon as any worker answer carries another `price_data`, so after a swap it serves the previous catalog for at most one request (PAGE LOAD SEQUENCE 6c.5). Responses keep the house `no-store` header and carry `ETag: "<sha256 of the JSON bytes>"`; a request whose `If-None-Match` equals it answers `304` with no body. The page sends `If-None-Match` itself from its own cache pointer, since `no-store` keeps the browser's HTTP cache out (PAGE LOAD SEQUENCE 6c.3-6c.5).

### 8.5 `POST run`

**Request.**

| Field | Type | Rule |
|---|---|---|
| `schema_version` | 1 | Required |
| `client_order` | `{page, seq}` | As the Backtest preview (`backtest.py:270-280`) |
| `data_version` | string or absent | Optional: the `price_data` of the page's catalog. A replica answers at that version while it holds it (the current one, or the previous one during `SCREENER_PREVIOUS_GRACE_S`); a newer version it does not hold yet answers 409 `DATA_VERSION_PENDING`, an older one 409 `DATA_VERSION_CHANGED` (MULTI-USER SCALE AND COST 6d.4) |
| `definition.universe.security_types` | `['stock']` | Only `stock` today (P15) |
| `definition.universe.sectors_in`, `sectors_out`, `industries_in`, `industries_out` | string[] | Values from `catalog.groupings`; an unknown value is refused with the allowed list. `Undefined` is not a value |
| `definition.universe.include_unclassified` | boolean | Default false: an include filter keeps a stock without that classification only when true; exclude filters never drop it (P15) |
| `definition.universe.price_min` | number ≥ 0 or null | Last close |
| `definition.universe.adv20_min_idr` | number ≥ 0 or null | `liquidity()` at E |
| `definition.universe.min_history_bars` | integer ≥ 1 or null | |
| `definition.universe.traded_on_eval_date` | boolean | Default true: stale tickers are hidden; false lists them, each row with the remark `STALE` (P4, decided 2026-10-28) |
| `definition.universe.exclude_price_breaks` | boolean | Default true: tickers with an unadjusted price break are hidden; false lists them with the row remark `PRICE_BREAK`, their values shown and each price-derived cell whose lookback contains the ex-date marked `PRICE_BREAK_IN_LOOKBACK` (P4 and P4.1 A, decided 2026-10-28) |
| `definition.universe.tickers` | string[] or null | Explicit list; each must be in `universe`; unknowns refused by name |
| `definition.universe.metric_filters` | Test[] (VALUE only) | ≤ `max_metric_filters` |
| `definition.conditions[]` | `{id, enabled, label?, test}` | `id` `^[0-9a-z]{1,6}$`, unique; ≤ `max_conditions` enabled |
| `definition.logic` | `all` \| `any` \| `at_least` | |
| `definition.at_least` | integer ≥ 1 | Required with `at_least`; above the active count means all (as the core) |
| `options.exhaustive` | boolean | Disables pruning |
| `options.explain` | boolean | Adds `plan` |

**Metric reference** (`MetricRef`): `{kind:'indicator', indicator:'I01'..'I53', params, output}` · `{kind:'price', field:'open'|'high'|'low'|'close'|'volume'}` · `{kind:'transform', fn, of: MetricRef, args}` · `{kind:'pattern', type, params}` · `{kind:'flow', metric, params:{window, board:'all'|'regular'}}` (`board` defaults to `'all'`, P8 decided) · `{kind:'xsection', metric:'return_rank', params:{window}}` · `{kind:'universe', attr}`. `params` are checked by the registry's `resolveParams` (unknown key, type, min/max, enum; never rounded) and by the overlay's narrowing.

**Test.**

| Kind | Shape | Rules |
|---|---|---|
| VALUE | `{kind:'value', metric, op:'gt'\|'lt'\|'between', value, value2?}` | `between` needs `value ≤ value2`, else `INVALID_CONDITION` with field `value2` |
| STATE | `{kind:'state', lhs: MetricRef\|{value}, op:'gt'\|'lt', rhs: MetricRef\|{value}}` or `{kind:'state', pattern}` | `price` vs output allowed only where `level_comparable` |
| EVENT | `{kind:'event', signal:{lhs, op:'crosses_above'\|'crosses_below', rhs} \| {pattern}, within}` | `within` 1..`within_max` (130 technical; flow maximum derived from the published window) |

**Response** (gzip, rows).

| Field | Content |
|---|---|
| `schema_version`, `versions`, `data` | 8.3 |
| `mode` | `screen` or `universe_only` (no active condition: the universe is listed) |
| `universe` | `{listed, eligible, stale_hidden, price_break_hidden, filtered_out}`: the two hidden counts are 0 when their chip is off (P4) |
| `conditions[]` | `{id, source:'precomputed'\|'dynamic'\|'flow'\|'xsection', metric, params_resolved, is_default, kind, unit, evaluated, passed, na, exhaustive, eval_date_basis}` |
| `need`, `match_count`, `near_count` | Integers |
| `rows[]` | Matches ∪ near rows: `{ticker, name, sector, industry, board:null, market_cap:null, last, chg_1d_pct, adv20_idr, last_bar_date, stale, remarks[], status:'match'\|'near', met, need, na_count, cells[]}`; `remarks[]` as in the universe body (P4) |
| `rows[].cells[]` | `{id, status:'pass'\|'fail'\|'na'\|'not_evaluated', value, lhs, rhs, unit, eval_date, event_date, bars_ago, market_sessions_ago, last_event_date, reason, remark}`; `reason` is the NA code; `remark` is null or `PRICE_BREAK_IN_LOOKBACK` (the value is shown and marked, P4.1 A; TARGET ARCHITECTURE §6.9) |
| `warnings[]` | For example `FLOW_LAGGED`, `PRICE_BREAKS_IN_RESULT` (with the count of rows and cells that carry a price-break remark), `NO_PRUNING_FOR_ANY` |
| `timings_ms` | `{queue, s0, s1, s2, s3, s4, total}` |
| `plan` | With `explain`: stages, order, survivors, cache hits |

A condition's `passed` counts the tickers in its `evaluated`; it equals the count over every eligible ticker only when `exhaustive` is true, and the page never shows a non-exhaustive count against the universe size (TARGET ARCHITECTURE §6.10). `board` and `market_cap` are always null and documented as "no data" (FACT: neither exists, `audit/fundamentals_universe.md` §4). Values are raw doubles rounded to 12 significant digits. Sorting, paging, search and CSV are done by the page: one response is one snapshot, so paging never re-runs the screen.

**Example** (shape only; ticker, name and numbers are illustrative, not market data):

```
POST /api/v1/screener/run
{"schema_version":1,"client_order":{"page":"pg_3f2a9c0d1e2b4a5c6d7e8f9012345678","seq":7},
 "definition":{"universe":{"security_types":["stock"],"price_min":50,"adv20_min_idr":1000000000,
   "traded_on_eval_date":true,"exclude_price_breaks":true},
  "conditions":[
   {"id":"a","enabled":true,"test":{"kind":"value","op":"lt","value":30,
     "metric":{"kind":"indicator","indicator":"I13","params":{"length":7},"output":"rsi"}}},
   {"id":"b","enabled":true,"test":{"kind":"state","op":"gt","lhs":{"kind":"price","field":"close"},
     "rhs":{"kind":"indicator","indicator":"I01","params":{"length":50},"output":"sma"}}},
   {"id":"c","enabled":true,"test":{"kind":"event","within":5,"signal":{"op":"crosses_above",
     "lhs":{"kind":"indicator","indicator":"I06","params":{},"output":"macd"},
     "rhs":{"kind":"indicator","indicator":"I06","params":{},"output":"signal"}}}}],
  "logic":"at_least","at_least":2},
 "options":{"exhaustive":false,"explain":false}}

200
{"schema_version":1,
 "versions":{"screener_engine":"0a1b2c3d4e5f6071","registry":"8192a3b4c5d6e7f8","screener_registry":"1f2e3d4c5b6a7980",
   "price_data":"<64 hex>","flow_data":null,"definition_hash":"<64 hex>"},
 "data":{"evaluation_date":"2026-10-27","price_through":"2026-10-27","flow_through":null,
   "broker_behind_sessions":0,"published_at":"2026-10-27T13:03:23Z"},
 "mode":"screen","universe":{"listed":844,"eligible":340,"stale_hidden":16,"price_break_hidden":8,"filtered_out":480},
 "conditions":[
   {"id":"a","source":"dynamic","metric":"I13.rsi","params_resolved":{"length":7,"source":"close"},"is_default":false,
    "kind":"value","unit":"index","evaluated":340,"passed":61,"na":0,"exhaustive":true,"eval_date_basis":"ticker_last_bar"},
   {"id":"b","source":"precomputed","metric":"I01.sma","params_resolved":{"length":50,"source":"close"},"is_default":false,
    "kind":"state","unit":"price","evaluated":340,"passed":120,"na":1,"exhaustive":true,"eval_date_basis":"ticker_last_bar"},
   {"id":"c","source":"precomputed","metric":"I06.macd x I06.signal","params_resolved":{"fast_length":12,"slow_length":26,
    "signal_length":9,"source":"close"},"is_default":true,"kind":"event","unit":"price","evaluated":171,"passed":40,"na":0,
    "exhaustive":false,"eval_date_basis":"ticker_last_bar"}],
 "need":2,"match_count":25,"near_count":118,
 "rows":[{"ticker":"XMPL","name":"Example Tbk","sector":"Financials","industry":"Banks","board":null,"market_cap":null,
   "last":1234,"chg_1d_pct":-1.2,"adv20_idr":45600000000,"last_bar_date":"2026-10-27","stale":false,"remarks":[],
   "status":"match","met":2,"need":2,"na_count":0,
   "cells":[{"id":"a","status":"pass","value":27.4,"unit":"index","eval_date":"2026-10-27","reason":null,"remark":null},
            {"id":"b","status":"fail","lhs":1234,"rhs":1250.5,"eval_date":"2026-10-27","reason":null,"remark":null},
            {"id":"c","status":"pass","lhs":-3.1,"rhs":-3.4,"eval_date":"2026-10-27","event_date":"2026-10-23",
             "bars_ago":2,"market_sessions_ago":2,"last_event_date":"2026-10-23","reason":null,"remark":null}]}],
 "warnings":[],"timings_ms":{"queue":0,"s0":2,"s1":0,"s2":3,"s3":95,"s4":12,"total":118}}
```

`is_default` is false for condition b because `length` 50 differs from the registry default 20, although `sma(50)` is pre-warmed for a preset (so `source` is `precomputed`): `source` says where the value came from, `is_default` whether the parameters are the registry's.

### 8.6 `POST preview`, `POST validate`, `POST counts`

**Preview request:** `{schema_version:1, client_order, definition, ticker, data_version}`. **Response:** `{versions, data, ticker, status:'match'|'near'|'fail'|'outside_universe', remarks[], met, need, cells[], bars:{d,o,h,l,c,v} (last 260), ihsg_close (aligned to the ticker's dates with asOf), overlays:[{condition_id, output, values}], markers:[{condition_id, bars:[{date, kind}]}], perf:{'1M','3M','6M','1Y': {stock_pct, ihsg_pct}}}`. The ticker's cells and status are returned even outside the universe. If `data_version` is older than the versions the replica holds (its current one, and the previous one during `SCREENER_PREVIOUS_GRACE_S`), the answer is 409 `DATA_VERSION_CHANGED`, and the page re-reads the catalog and re-runs the screen; a newer one is `DATA_VERSION_PENDING`, handled by edge-bff (§8.8).

**Validate request:** `{schema_version:1, definition}`. **Response:** `{valid: true, definition_hash, normalized}` or the 422 error of the first problem, with `field` and the fix. The built answer also carries `versions`, an additive field (core/worker integration, 2026-10-28): the versions of the snapshot the definition was checked against, so edge-bff stores `registry` and `screener_registry` with a saved item from the same answer that validated it (`apps/edge-bff/screener/src/core/contract.ts` `ValidateResponse.versions`; `apps/screener-worker/CONTRACT.md` route table; `apps/screener-worker/src/server.ts` `/v1/validate`). A reader that ignores it loses nothing.

**Counts request:** `{schema_version:1, data_version?, definitions:[{item_id, definition}]}` (≤ 50; `data_version` as in `run`). **Response:** `{versions, data, counts:[{item_id, match_count, near_count} | {item_id, error}]}`, cached per (`price_data`, `definition_hash`).

### 8.7 Saved items and watchlist

| Route | Request | Response | Errors |
|---|---|---|---|
| `GET items?kind=` | — | `{items:[{item_id, kind, name, definition, schema_version, registry_version, screener_registry_version, definition_hash, revision, created_at, updated_at, needs_review:[{field, reason}]}]}` | — |
| `PUT items/{item_id}` | `{kind, name, definition, revision?}` (no `revision` = create) | The stored item | 422 validation; 409 `REVISION_CONFLICT`; 409 `NAME_TAKEN`; 422 `LIMIT_EXCEEDED {limit:'saved_items'}` |
| `DELETE items/{item_id}` | — | 204 | 404 `NOT_FOUND` |
| `GET watchlist` | — | `{tickers:[{ticker, added_at}]}` | — |
| `PUT` / `DELETE watchlist/{ticker}` | — | 204 | 422 `INVALID_INPUT` (ticker rule); 422 `LIMIT_EXCEEDED {limit:'watchlist'}` |

`needs_review` comes from re-validation on load: a parameter that left the registry range is shown with its field and never adjusted.

### 8.8 Errors

| Status | Code | When | Details / fix shown |
|---|---|---|---|
| 422 | `INVALID_INPUT` | Malformed JSON, unknown field, `loads()` refusal | `field` |
| 422 | `INVALID_CONDITION` | Wrong test shape, `value > value2`, operator not allowed for the output | `field`, allowed values |
| 422 | `UNKNOWN_INDICATOR` | Id not in the generated registry (`screener-registry.json`; I01-I53 today, so a registry release that adds Ichimoku needs no code change here) | the allowed ids, from the same file |
| 422 | `PARAM_OUT_OF_RANGE` | Parameter outside min/max or the derived cap | `{field, min, max}` |
| 422 | `METRIC_UNAVAILABLE` | Metric with no data or no decision | `{metric, availability, reason}` |
| 422 | `LIMIT_EXCEEDED` | Any limit of 8.9 | `{limit, allowed, needed}`; `costliest` for `compute_budget` |
| 424 | `DATA_UNAVAILABLE` | No snapshot can serve (first start, files missing) | "No published data is loaded yet; it loads after the next publication or within minutes of a restart; try again later" |
| 424 | `DATA_INTEGRITY` | A file failed its sha256, size or cross-check, and no previous version exists | "The latest publication failed its checks and no earlier one is loaded; it retries at the next publication" (with a previous version, it keeps serving and the catalog shows `failed_keeping_previous`) |
| 409 | `BUSY` | Worker queue full | "The screener is busy; retry in a few seconds" |
| 409 | `SCREEN_REPLACED` / `PREVIEW_REPLACED` | A newer call of the same page arrived | "A newer request replaced this one"; the page shows the newer answer, nothing to do |
| 409 | `DATA_VERSION_CHANGED` | A preview, run or counts request pinned to a data version older than the replica holds | "New data was published; the screen is re-run" (the page re-reads the catalog and re-runs) |
| 409 | `REVISION_CONFLICT`, `NAME_TAKEN` | Saved item conflict | Reload, save as a copy, or rename |
| 404 | `NOT_FOUND` | Saved item absent for this owner | "This saved item no longer exists; reload the list" |
| 413 | `REQUEST_TOO_LARGE` | Body > 131,072 bytes (house middleware) | "The definition is too large: remove conditions or filters" |
| 503 | `SCREENER_DISABLED` | No worker URL configured | "The screener is switched off on this environment" (an operator sets `SCREENER_WORKER_URL`) |
| 503 | `SCREENER_NOT_READY` | Tables missing, or the worker has no snapshot yet (`Retry-After`) | "The screener is starting; retry after the stated seconds" |
| 503 | `SCREENER_UNAVAILABLE` | Worker unreachable or answered outside its API | "The screener service cannot be reached; retry shortly" |
| 504 | `TIMEOUT` | Worker deadline passed | "The screen took longer than the limit: fewer custom conditions or shorter lengths", with the costliest condition |

`DATA_VERSION_PENDING` (worker 409, a replica that has not yet loaded the page's publication) never reaches the page: edge-bff retries once on a new connection, then answers 503 `SCREENER_NOT_READY` with `Retry-After: 2`, which the page already handles (MULTI-USER SCALE AND COST 6d.4, 6d.6).

Every refusal names the field (where there is one) and the fix, and every limit is published in the catalog before the user meets it. This follows the AGENTS.md gate rule: (a) the rule is visible before writing (`limits[].rule`), (b) how to pass it, (c) one right and one wrong example (`limits[].example_ok`, `example_refused`, generated from the value, never typed into the page), and (d) a refusal that names where the problem is and how to fix it (the last column above).

### 8.9 Limits

Initial values are provisional (P5) and are replaced by the Phase 17 measurements. Worker limits come from the environment with no defaults, so the service does not start without them (backtest-worker convention, `audit/edge_conventions.md` §1.4).

| Limit | Initial value | Enforced by | Basis |
|---|---|---|---|
| Active conditions | 20 (`SCREENER_MAX_CONDITIONS`) | worker `validate.ts` | PROPOSED; Backtest allows 32 (`BACKTEST_MAX_CONDITIONS`) |
| Universe metric filters | 8 (`SCREENER_MAX_METRIC_FILTERS`) | worker | PROPOSED |
| `within` (technical) | 130 sessions (`SCREENER_WITHIN_MAX`; the snapshot tail is this + 1, TARGET ARCHITECTURE §6.7) | worker | The prototype's marker window (`audit/html_model.md` §4.2) |
| `within` + window (flow) | Derived from the published window (130 sessions F06; 41 F05) | worker | Phase 2 |
| Indicator lengths | Derived cap per parameter (cost rule, `SCREENER_CAP_BUDGET_MS`) | worker; published as `max` | FACT inputs: CCI(1000) 7.93 s, O(N) ≤ 0.09 s at n = 1000 |
| Compute budget | `SCREENER_MAX_CPU_MS` | worker cost model | Phase 17 |
| Worker deadline | 20 s (`SCREENER_DEADLINE_MS`) | worker → 504 | Phase 17 |
| In flight per (owner, page) | 1 screen, 1 preview (latest wins) | edge-bff | Backtest precedent, narrowed from owner to (owner, page) (MULTI-USER SCALE AND COST 6d.6) |
| Running per owner tag, per worker replica | 2 (`SCREENER_OWNER_INFLIGHT`); further requests wait in the owner's lane, served round-robin across owners | worker | PROPOSED (6d.6); set by S23 |
| Previous snapshot kept after a swap | 600 s (`SCREENER_PREVIOUS_GRACE_S`) | worker | PROPOSED (6d.4); set by S22 |
| Worker queue | 4 (`SCREENER_QUEUE`) | worker → 409 `BUSY` | Phase 17 |
| Request body | 131,072 bytes | edge-bff middleware | FACT |
| Saved definition | 65,536 bytes JSON | DB CHECK and edge-bff | Migration 1 |
| Saved items, watchlist | `SCREEN_LIMIT`, `WATCHLIST_LIMIT` (P12 a decided; values set in Phase 1, PROPOSED at most 500 each, the `PIN_LIMIT` precedent) | edge-bff store | `apps/edge-bff/app/store.py:319-320` (main `010af1e`) |
| Counts request | 50 definitions (`SCREENER_MAX_COUNTS`, at least `SCREEN_LIMIT` so every saved screen can be counted in one call) | worker | PROPOSED |
| Response | ≤ 2 MB JSON (`SCREENER_MAX_RESPONSE_BYTES`) | worker | INFERENCE; FACT: 845 × 5 values = 112 KB JSON / 37 KB gzip |
| Download per xsection file | `SCREENER_MAX_FILE_BYTES` (gzip bytes, checked against the index's `bytes` before any grant or download) | worker refresh → `REFRESH_FAILED {limit:"file_bytes"}`, previous version kept | 2 × the U4/S14 measurement |
| Inflated size per file | `SCREENER_MAX_INFLATED_BYTES`, passed as `TerminalClient`'s `maxFileBytes`, the cap `inflateVerified` applies (`apps/backtest-worker/src/terminal.ts:74, 493`) | worker refresh → `REFRESH_FAILED {limit:"inflated_bytes"}` | INFERENCE: the `price` document is about 75-80 MB inflated |
| Bytes per refresh | `SCREENER_MAX_REFRESH_BYTES` (sum of the files one refresh downloads) | worker refresh → `REFRESH_FAILED {limit:"refresh_bytes"}` | The sum of the per-file caps |

Every worker limit above is an environment variable with no default (TARGET ARCHITECTURE §6.17; CHANGES AWAITING APPROVAL A4); edge-bff's limits follow its own config pattern.

### 8.10 Versions and caching

| Cache | Key | Invalidated by | Where |
|---|---|---|---|
| Snapshot (defaults, tails, attributes, ranks, preset counts) | `price_data` + `screener_engine` | A new `finished_at` | worker memory |
| Series LRU (custom parameters) | (`price_data`, `screener_engine`, id, canonical params, output) | Version swap; `SCREENER_CACHE_BYTES` | worker memory |
| Result cache | (`price_data`, `screener_engine`, `screener_registry`, `definition_hash`) | Version swap (after the grace window) | worker memory (gzip bytes), per replica |
| Files | sha256 | Disk LRU | worker disk (`SCREENER_CACHE_DIR`, `TerminalClient` `DiskCache`) |
| Catalog, universe | (`price_data`, `screener_registry`) | Version change seen on `/health` (≤ 60 s), or a worker answer at another `price_data` (at once); replaced only by a later `published_at`, never by an older one | edge-bff memory, as gzip bytes with their `ETag` |
| Last catalog, universe and result of the last open screen (bytes) | sha256 of the bytes (= the `ETag`); pointer `localStorage scr.boot` names them with their `versions` and the login | A pointer at other `versions`, or of another login, is dropped at boot; bytes age out of the shared 50 MB LRU | browser IndexedDB `terminal-files` through `rack.ts` `fileCache()` (PAGE LOAD SEQUENCE 6c.3, P24) |
| Saved items | — | Never cached | edge-bff DB |

### 8.11 Worker private API

Header `x-screener-worker-key` (≥ 32 characters) on every route except `/health`; private host only (`http://screener-worker.railway.internal:8080`); errors in the contract shape; no secret in any log. edge-bff also sends `x-screener-owner`, an opaque tag (the first 16 hex of HMAC-SHA256(`SCREENER_WORKER_KEY`, `owner_key`)), on every call except `/health` and `/ready`, so the worker can share its threads fairly per owner without learning the owner's key. The worker answers `run`, `preview` and `counts` gzip-encoded, and edge-bff relays the bytes without parsing a 2xx body (MULTI-USER SCALE AND COST 6d.5, 6d.6).

| Route | Purpose |
|---|---|
| `GET /health` | Liveness; versions; snapshot age; refresh state (no key) |
| `GET /ready` | 200 only with a loaded snapshot |
| `GET /v1/catalog`, `GET /v1/universe` | As 8.4 |
| `POST /v1/run`, `POST /v1/preview`, `POST /v1/validate`, `POST /v1/counts` | As 8.5-8.6; deadline `SCREENER_DEADLINE_MS`; cancel when the caller disconnects |

### 8.12 terminal-api additions (CLI deploy)

FACT (main `010af1e`): `GET /api/terminal/v1/state` already exists (EXEC-BACKTEST-LOAD K1; terminal-api deployment `689dc465`; `apps/terminal-api/app/main.py:297-305`). It is `Depends(subscriber)`: the gateway proxy key or a direct subscriber's session cookie (`main.py:165-179`). PROPOSED: it keeps that access, because it grants no file; `POST /xsection` is new and accepts only a caller with `x-terminal-proxy-key` (the gateway mechanism, `main.py:26, 149-154`). Neither route is in the edge-bff browser allow-list (`apps/edge-bff/app/main.py:34-36`).

| Route | Request | Response | Quota / audit |
|---|---|---|---|
| `GET /api/terminal/v1/state` (exists; one field added) | — | FACT: `{finished_at, price_through, broker_through, broker_behind_sessions}` from `Bucket.state()` (`bucket.py:45-53`, refreshed by `Bucket._fresh`, 27-43; 503 `state_unavailable` when unreadable). PROPOSED addition: `xsection:{name:{key, sha256, bytes, rows, as_of}}`, one field added to `STATE_FIELDS` (`bucket.py:8`) | None (FACT) |
| `POST /api/terminal/v1/xsection` (new) | `{names: ['price','actions', ...]}` (each name present in the index; unknown names refused with the indexed list) | `{finished_at, expires_in_seconds, encoding:'gzip json', files:[{name, url, sha256, bytes, rows, as_of}]}` | One audit row through the existing helper: `store.log_access(c, sid, 'file', quota.REF, ip, dataset='xsection', keys=[...], bytes_=...)` (`store.py:70-75`). `terminal.access_log` requires a ticker matching `^[A-Z0-9]{1,12}$` and a `kind` in `file`, `history_price`, `history_broker` (migration `20261025_100:47-57`); the `REF` pseudo-ticker, as reference files use (`main.py:278-280`, `quota.py:5`), fits both and never counts as an opened ticker, so no terminal-schema migration is needed. File quota = number of names; bytes counted |

The worker asks `/xsection` only for the files its caches lack (TARGET ARCHITECTURE §6.5, refresh rule 2). Tests: `/xsection` refuses a caller without the proxy key, a direct subscriber included; `/state` returns `xsection` when `state.json` holds it, and its existing tests (`test_state_names_the_publication_without_quota_or_audit`, `test_state_unreadable_is_503`) stay unchanged (TEST PLAN 10b.11).


## FRONTEND INTEGRATION

Approval item 13. Everything here is **PROPOSED** unless labelled. The prototype inventory it builds on is APPENDIX A (prototype UI to backend mapping) and `audit/html_ui.md`; the backend it calls is API CONTRACT. Labels and evidence notation as in TARGET ARCHITECTURE.

### 9.1 Delivery

- **A Vite + TypeScript sub-app, `apps/edge-bff/screener/`**, built like the Backtest page (FACT precedent, `audit/html_ui.md` §5.2): `base:'/screener-app/'`, one IIFE classic script at the end of `<body>`, `cssCodeSplit:false`, build modes production, smoke and fixture. FACT: the sub-app CSP forbids inline scripts (`apps/edge-bff/app/main.py:39-48`), and the prototype is inline script.
- **Framed at `/screener`** like Terminal and Backtest, under a new `SCREENER_CSP` with `connect-src 'self'` only: the page fetches nothing from the bucket, because the preview is server-computed.
- **A thin client.** The production bundle contains no formula code. It imports only `screener/src/core/contract.ts` (types) and `universe.ts` (the same filter function the worker runs). A bundle test proves that no `indicators.ts`, `conditions.ts` or fixture code is present.
- **A 1:1 port of the prototype layout and CSS**, module by module (state, universe, presets, builder, browser, results, preview, dialogs, storage), with the visible catalogue changes listed in 9.2 (P6, P11). Words inside the app stay in the app (`src/texts.ts`, as Backtest's `api/texts.ts`); shell words go in `static/edge-labels.js` (AGENTS.md).
- **`lightweight-charts` 5.2.1 from npm** instead of the prototype's 197 KB inline copy. FACT: the same version Terminal and Backtest pin (`audit/html_ui.md` §1 item 8).
- **Data behind a `ScreenerApi` interface** with a `live` implementation (`/api/v1/screener/*`, CSRF from `/api/v1/auth/session`, as `backtest/src/api/live.ts`) and a `fixture` implementation that keeps the prototype's synthetic data for the 1:1 visual test only.
- **Loading states** reuse the shared ring of the rack pages, `apps/edge-bff/terminal/src/ui/spin.ts` with `styles/spin.css` (EXEC-BACKTEST-SPIN: one ring for every page that reads the rack, 0.15 s per turn, 1.6 s with reduced motion; `EXEC.md:8464-8473`), for the catalog, a run and the preview chart; the preview chart is emptied while a new ticker loads, never showing the previous ticker's candles (the class of the ERRORS entry EXEC-BACKTEST-SPIN). FACT: ERRORS also records, for the next rack pages (macro, cross-asset), the EXEC-BACKTEST-LOAD pattern: draw first, load when needed, decode in a Web Worker, keep derivations per publication, with `rack.ts` (the Lesson of the ERRORS entry EXEC-BACKTEST-LOAD). The Screener page draws first and loads when needed. It downloads no rack file in this design (9.3; TARGET ARCHITECTURE C2), so it needs no Web Worker decode; it reuses `rack.ts` `fileCache()` and `sha256Hex()` to keep its last catalog, universe and result by sha256 in the same browser cache (PAGE LOAD SEQUENCE 6c.3, 6c.8; P24). Each waiting state is tested with data that really arrives late (M253). The order in which the page asks for its data after the browser opens, following the Terminal and Backtest sequence, is designed in PAGE LOAD SEQUENCE.
- **Text rendering.** Company, sector and industry names and saved-item names render as text nodes, or through the prototype's `esc()` without exception. FACT: the prototype has 39 `innerHTML` writes with `esc()` (`audit/edge_conventions.md` §2.1); EDGE's rule is text nodes for untrusted text (`apps/edge-bff/README.md:11`).

### 9.2 Plan per prototype area

Plan classes: **KEEP** = kept 1:1 with real data; **CHANGE** = changed (reason given); **DISABLED** = shown disabled with a reason (no data or no decision); **NEW** = new. They describe what the port does with each area; APPENDIX A's codes (S, I, C, N, D: the brief's five classes) describe what each capability requires, and the two are not interchangeable. The CHANGE items that are design preferences rather than integration needs (Copy link, theme and search in the shell, delete confirmation, `between`, per-condition bandar thresholds, pagination, the notation default, the `kxd_os` label) were put to the user as one decision, P22, accepted as recommended with the go (2026-10-28).

| Prototype area (code) | Data from | Plan | Class and reason |
|---|---|---|---|
| Top bar (`header.top[hidden]`, global search, ⌘K, theme, nav) | — | Stays hidden; ticker lookup moves into the page (results search and a preview lookup field, reusing `backtest/src/picked.ts` `searchMatches`: ticker prefix, then name substring); the shell keeps ⌘K | CHANGE: the shell owns the top bar, search and theme (`audit/html_ui.md` §3.1, §5.1) |
| Theme | `localStorage edge-auth-monitor-theme` | Read at boot, follow later changes through the `storage` event (INFERENCE: fired in same-origin frames); prototype key `edge-scr-theme` dropped | CHANGE: one theme for EDGE |
| Page head: name, source pill, data line | `catalog.data` | "IDX equities (844 listings) · close `evaluation_date` · published `published_at`"; Phase 2 adds "flow through `flow_through`" | KEEP, CHANGE (real counts and dates instead of "94 sample listings") |
| Reset, Save, Export menu | — | Kept; "Duplicate as new screen" kept; "Method & sources" kept | KEEP |
| Universe quick filters | `catalog`, `universe` | Sector and Industry (include, exclude; lists and counts from `catalog.groupings`: 11 sectors and 58 industries, with the unclassified stocks shown apart as "Unclassified (n)" and kept by an include filter only through an explicit option (P15); Liquidity: ADV20 ≥ Rp B and Price ≥ Rp (prototype defaults 1 B and 50 kept); Index, Board, Market cap and Free float pills shown disabled with "no data" reasons | KEEP for sector, industry, ADV, price; DISABLED for the rest (FACT: no data, `audit/fundamentals_universe.md` §4.1) |
| New universe chips and remarks | `universe`, `run.rows[].remarks`, `cells[].remark` | Two chips, on by default and removable: "Traded on `E`" hides stale tickers and "No unadjusted price break" hides tickers with a price break, each naming how many it hides. Turned off, the hidden tickers are listed with a Remark column (and the same remark on the preview): "Stale: last trade `<date>`" or "Price break: `<action>` ex `<date>`, history not adjusted", worded in `src/texts.ts` from the API's codes. Values stay visible (P4.1 A); each cell marked `PRICE_BREAK_IN_LOOKBACK` gets a mark and a tooltip with the ex-date | NEW (P4, decided 2026-10-28): stale tickers (16) and tickers with an unadjusted price-affecting action (a derived rule; 8 on 2026-10-27, TARGET ARCHITECTURE §6.12) would otherwise show false signals unannounced; TEMPORARY for price breaks until the D22 data-layer fix |
| Special notation | — | The checkbox is disabled and **off** (prototype default on); its chip "Excludes special notation" is removed | CHANGE (P11): a default-on filter with no data would be a silent no-op |
| "In universe X of N" | `universe.ts` locally | Computed in the page from `/universe` on every edit; the worker re-applies the same function | KEEP |
| More filters drawer: metric filters | `catalog.metrics` | Technical and flow VALUE filters; fundamental entries disabled with reasons; "Add metric filter" no longer defaults to ROE (it opens the picker) | CHANGE: ROE has no data |
| Presets: tabs, chips, counts, overflow | `catalog.presets` | Counts come from the catalog (computed once per publication), not from 26 browser screens at boot. Unavailable presets stay visible, disabled, with their reason in the tooltip naming the unavailable legs; a preset never runs with a leg removed, and "Load without the unavailable legs" is an explicit action that lists the dropped legs (TARGET ARCHITECTURE §6.12, with the phase of each preset) | CHANGE (cost), DISABLED (11 fundamental and combined presets; 6 bandarmology presets until Phase 2/3; Ichimoku until a registry release) |
| My screens tab | `GET items?kind=screen` | Server list; Duplicate kept; Delete asks for confirmation (a server delete cannot be undone, unlike the prototype's local list) | CHANGE (P12) |
| Match control (All / Any / At least n) | — | Kept; the number input is bounded by the active count | KEEP |
| Adder type-ahead, synonyms, "/" shortcut, quick rail | `catalog` | Kept; entries come from the catalog (53 registry indicators plus transforms, patterns, flow and universe items); the 17 legacy technical entries become presets or transform entries mapped onto the registry (TARGET ARCHITECTURE §6.9); synonyms come from the catalog (`indicators[].synonyms`, kept in the overlay; the page holds none); the quick rail's ROE entry replaced by an available metric | CHANGE (P6): one indicator per formula, no duplicates (10 indicators existed twice) |
| Indicator browser dialog | `catalog.indicators` | Kept, with real min/max (derived caps), typed booleans, `not_accepted` parameters hidden, history class shown ("level depends on history start" for cumulative indicators) | CHANGE: the prototype's `XPARAM` had no min/max and string booleans (`audit/html_model.md` §2.4) |
| Condition card: Default/Custom, parameter grid | `catalog` | Kept; invalid input is refused in place with the field and the allowed range, never rounded or ignored (prototype: rounds step-1 fields and ignores values ≤ 0) | CHANGE (I7) |
| Operators and "within N sessions" | `catalog` tests | Kept; `between` refuses `value > value2` instead of reordering; `within` 1-130 | CHANGE (I7) |
| Per-condition pass count | `run.conditions[].passed`, `evaluated`, `exhaustive` | Rendered in each card as "m of U pass" when the condition is exhaustive, else "m of n evaluated" with the tooltip "counted on the tickers that can still match or be near; run exhaustively for the full count" (TARGET ARCHITECTURE §6.10). FACT: the prototype computes it but no markup shows it (`audit/html_ui.md` §3.15) | NEW |
| Save as My metric | `PUT items` (`kind:'metric'`) | Kept, server-side | CHANGE (P12) |
| Results meta line, near toggle | `run` | Kept; the near toggle is local (near rows are always in the answer) | KEEP |
| Results search | local | Kept (symbol or name substring) | KEEP |
| Columns: Symbol, Company, Sector, Last, 1D, Avg value, Met, one per condition | `run.rows` | Kept with real values; cell tooltips show `eval_date`, `event_date`, `bars_ago`, NA reason or cell remark; a Remark column appears when a shown row carries a remark (P4) | KEEP, NEW (Remark column) |
| Column Mkt cap | — | Shown greyed, "no data" tooltip, not sortable; default tie-break uses ADV20 instead of market cap | DISABLED (EXEC-MCAP waits for "go") |
| Sort, pagination, selection, bulk bar | local | Kept, client-side over at most about 845 rows. Pagination returns to page 1 only when the row set or its order changes (a new result, search, near toggle, sort), not on other edits | CHANGE: the prototype's `refresh()` set page 1 on every edit (`audit/html_ui.md` §3.13) |
| Watch buttons and bulk "Add to Watchlist" | `watchlist` routes | Server watchlist (P12); no Watchlist page in scope (decision) | CHANGE |
| Row click → preview | `POST preview` | Kept; rows become keyboard-reachable (`tabindex`, Enter) | CHANGE (accessibility) |
| Empty states | `run` | Kept ("Show near misses (n)", "Match at least n−1", "Reset universe") | KEEP |
| Detail head, quote, status pill | `preview` | Kept; the status pill uses the one near rule (prototype showed "Near 0/1") | CHANGE (`audit/html_ui.md` §3.15) |
| "industry · board · indexes" line | `preview`, `catalog` | Industry shown; board and index membership shown as "no data" | DISABLED |
| Chart / Performance tabs | `preview` | 9.3 | KEEP, CHANGE |
| "Why it passed / did not pass" | `preview.cells` | Server cells with value, date, event date, bars ago and NA reason | KEEP |
| Fundamentals facts (8 fields) | `catalog.fundamentals` | Each shown as "no data" with its reason; dividend yield from Phase 2 | DISABLED |
| Copy summary | local | Kept; adds the evaluation date | KEEP |
| Method & sources view | `catalog` | "How conditions work" rewritten to the real semantics (VALUE / STATE / EVENT, evaluation date, stale rule); preset sources kept; the sample-data note replaced by the data status. The editable global bandar thresholds become per-condition parameters (Phase 3, P9) | CHANGE |
| Send to Backtest dialog | `POST validate` | 9.4 | CHANGE |
| CSV export | local | 9.6 | CHANGE |
| Toast | — | `aria-live="polite"` | CHANGE (accessibility) |
| Dialogs and drawer | — | `aria-modal`, focus trap, focus return to the opener; `aria-sort` on sortable headers; arrow keys on `role=tab` segments | CHANGE (accessibility gaps, `audit/html_ui.md` §3.14) |
| "Clear all" and liquidity clears | — | One rule: "Clear all" and both liquidity clears return to the documented defaults | CHANGE (the prototype left two chips and had two different clears) |

### 9.3 Preview chart path

1. Row click (or lookup) → `POST /api/v1/screener/preview {definition, ticker, data_version}` (debounced, latest wins).
2. The answer carries the last 260 bars, IHSG closes aligned to the ticker's dates with `asOf`, overlay tails per active condition, event markers per condition, the ticker's cells and status, and the rebased performance figures.
3. The chart draws the last 130 sessions as the prototype does: `CandlestickSeries`, one `LineSeries` per overlay output (dashed for band lines), and `createSeriesMarkers` with `arrowUp` per event bar in the condition's colour. This is the pattern of `apps/edge-bff/backtest/src/signals.ts` `initPriceChart` (FACT: same library and API, `audit/html_ui.md` §5.2); that module is bound to the Backtest page state, so the pattern is reused, not the module.
4. "Stock vs IHSG" (the relabelled performance view, P14) is drawn from the same answer, 1M/3M/6M/1Y, as the prototype's inline SVG. The session counts come from `catalog.periods` (one named entry: 21/63/126/252 as EDGE's fast-lane defaults and I33's annualization use, P23 a, accepted with the go; the prototype used 250 for the year), not from page code.
5. If the data version moved, the worker answers 409 `DATA_VERSION_CHANGED` and the page re-runs the screen, so chart and table never mix two publications.
6. New action "Open in Terminal": sets `localStorage 'ml.symbol'` (FACT: the Terminal reads it at boot, `apps/edge-bff/terminal/src/main.ts:118` at `010af1e`) and posts `{type:'edge-nav', route:'terminal'}` to the shell.

Rejected: the per-ticker `/bundle` plus in-browser recompute (TARGET ARCHITECTURE §6.18, C2). It would put formula code in the page, cost a grant per click and need a drift check between page and worker. Also weighed: bars only from the shared rack loader (`apps/edge-bff/terminal/src/data/rack.ts`, EXEC-BACKTEST-LOAD K3 A), with cells, overlays and markers from the worker. Not chosen now, because each previewed ticker would cost a `/bundle` grant against the shared subscriber's 30 tickers per hour and could come from a newer publication than the worker's snapshot (C2); the page reads no rack file, so K3's one loader stays the only browser loader.

### 9.4 Send to Backtest handoff (Phase 1b)

- The dialog keeps the prototype's table: each condition marked "Entry rule" or "Left out" with the reason from `to-backtest.ts` (TARGET ARCHITECTURE §6.15).
- Limits come from the Backtest: the page reads `GET /api/v1/backtests/catalog` `limits` (`max_portfolio_tickers`, `window_bars`, `max_conditions`) before it builds the handoff (TARGET ARCHITECTURE §6.15).
- Tickers: the previewed ticker (single), or the selection, or the matches. Above `max_portfolio_tickers` (12 today), that many top tickers by the current sort are preselected and editable (P13); fewer than 2 disables portfolio mode, as the prototype does.
- "Open in Backtest": validate through `POST validate`, write the one-shot `sessionStorage['edge-backtest-import']`, then post `{type:'edge-nav', route:'backtest'}`. The handoff carries the whole portable definition (`definition`, canonical JSON), the cards, and every left-out condition in its original wire form with its reason (`left_out[].condition`), plus each sent ticker's pack sha256 (shape in §6.15); the Backtest keeps `definition` beside its cards for a later release.
- The shell (`static/index.html`) accepts `edge-nav` only when `event.origin === location.origin` and `event.source` is its own frame, and only for routes `backtest` and `terminal`. No data travels in the message or the URL.
- "Download JSON" is kept (the same object). "Copy link" (`backtest.html#import=<base64>`) is dropped: the design keeps data out of URLs and history, and the target file does not exist in EDGE (FACT, `audit/html_ui.md` §3.10).
- The Backtest page reads and deletes the key once at the start of `boot()` and applies it when its catalog is known, in `boot()` or in `catalogArrived()` (page-only change on the page as EXEC-BACKTEST-LOAD left it; worker untouched; §6.15).

### 9.5 Saved screens, My metrics, watchlist

- P12 (a), decided 2026-10-28: `GET/PUT/DELETE items` and `watchlist` routes. Save shows "A screen with this name exists" as the prototype does; a stale `revision` answers 409 and the dialog offers reload or save as a copy.
- On load, `needs_review` fields are highlighted on their cards; nothing is adjusted silently.
- The saved definition is the portable definition (the same object used for run, CSV metadata and Send to Backtest), plus sort and near-toggle state.
- `localStorage scr.*` keeps only conveniences: panel sizes, preview open, last open screen, and the `scr.boot` pointer to the cached catalog, universe and last result (PAGE LOAD SEQUENCE 6c.3, P24). Saved screens and the watchlist always come from the server.

### 9.6 CSV export

- Client-side Blob, named `<screen-name-slug>-<evaluation_date>.csv` (prototype rule).
- Rows: the visible rows in the **current sort** (search and near toggle applied, every page). FACT: the prototype's "selected" export used universe order (`audit/html_ui.md` §3.10); fixed.
- Metadata header lines: screen name, `evaluation_date`, `published_at`, `price_data_version`, `registry_version`, `screener_registry_version`, `definition_hash`, and "market cap: not available".
- Columns: Symbol, Name, Sector, Industry, Last, 1D %, Avg value 20D (Rp B), Status, Met (m/n), Remark (the row remark code and its date, empty when none; P4), then per condition: value, status, event date, bars ago (and the NA reason or the cell remark).
- Text cells that begin with `=`, `+`, `-` or `@` are prefixed with an apostrophe (spreadsheet formula injection); numeric cells are written as numbers.

### 9.7 Shell and image touch points (FACT: the Backtest precedent, `audit/edge_conventions.md` §1.7-1.8, §2.4)

| Place | Change |
|---|---|
| `static/index.html` | Nav array entry; Shell's enabled-route list; `ScreenerPage` (Shell + `<iframe class="terminal-frame" src="/screener-app/">`); `App.currentPath`; `go()` allow-list and path map; render switch; `message` listener for `edge-nav` |
| `static/edge-labels.js` | `screener: {nav: "Screener", frameTitle: "Stock screener"}` |
| `app/main.py` | `@app.get('/screener')`; `SCREENER_APP`; page and asset routes; `SCREENER_CSP`; mount `screener.routes` |
| `Dockerfile`, `.dockerignore` | `screener` Node stage; `COPY --from=screener`; ignore rules |
| Tests | Tab list `['Monitor','Terminal','Backtest','Screener']`; image COPY list; labels come from `edge-labels.js` |
| `README.md` (edge-bff) | "Screener tab" section |

**Behaviour.** Condition and parameter edits are debounced 350 ms with latest wins (`client_order`). Sort, page, search, near toggle and CSV never call the server. Preset counts come from the catalog, not from 26 screens at boot.


## TEST EVIDENCE

This section lists what was actually verified during the read-only audit of 2026-10-27, and what was not.

**How the checks were run.**
- All checks were read-only:
  - PostgreSQL through pgweb with SELECT and EXPLAIN only (role `pgweb`, statement timeout 30 s);
  - repository modules imported unchanged (`node --experimental-strip-types`, node v22.22.0);
  - TA-Lib 0.6.8 on C 0.6.4 in a scratch Python 3.13 venv.
- No file in `/home/user/saniti` was changed. No Railway or EDGE HTTP call was made.
- Each check has two passes: the area auditor's, then an adversarial verifier's. Where the verifier refuted or corrected a figure, the corrected figure is given and the change is noted.

**Evidence.** Evidence notation as in the header: `audit/<area>.md` and `audit/verify_<area>.json` (reports and verifications), `evidence/<area>/<file>` (raw outputs), all relative to `verification/screener/`; repository `path:line` citations are at `main` `010af1e`.

**Labels.**
- FACT: measured or seen in this audit.
- INFERENCE: concluded from facts.
- PROPOSED: a recommendation.
- UNKNOWN: not established.

**No screener code existed** in the repository at the audit (FACT at `010af1e`: `apps/edge-bff/static/index.html` holds 33 `screener` lines, all CSS; no other source hit; `audit/verify_flow.json` C17). Every check below is a component or data check. None is an end-to-end test of a screener. Phase 1 code began on the branch after the go (commit `8a236eb`); its tests are TEST PLAN's, recorded as they run.

---

### 10.1 Summary

| ID | What was verified | Result in one line | Label |
|---|---|---|---|
| T1 | `F` (terminal `indicators.ts`) vs stored Feature 04, Feature 01 and derived columns | Equal across the universe (max rel 1.25e-15); 9 of 53 indicators fully served at defaults, 2 partly | FACT |
| T2 | `F` vs TA-Lib 0.6.8 / C 0.6.4 | Equal for every TA-Lib-backed indicator, but 4 TA-Lib functions follow other conventions and must not be called directly | FACT |
| T3 | The prototype's own engines vs `F` | 43 of 53 equal on 5 tickers over the last 250 bars; 10 differ; a second legacy engine exists | FACT |
| T4 | Tail window vs full history | Default lengths are safe from about 500-750 bars, except cumulative indicators, KAMA, KVO and EOM. Long custom lengths and cumulative or EMA-based states need full history. | FACT |
| T5 | VALUE / STATE / EVENT semantics on live bars | Derivable from the shared core; Donchian same-bar trap confirmed market-wide | FACT |
| T6 | Feature 04 unit tests | 49 passed (twice); 2 database-bound files not run; no CI | FACT |
| T7 | Feature 04 live data checks | Healthy and complete vs price, but no stock is gap-free against the true calendar, and live splits distort values | FACT |
| T8 | Flow formula checks | Avg Buy, price volume, trade count, foreign % of value and stored windows reconcile | FACT |
| T9 | ADV vs exact traded value | close × volume vs exact Regular value: 20-session mean median 0.67%, p90 2.57%, max 15.3% (1 day: median 1.45%, max 14.8%); 2 stocks cross the 1 B threshold | FACT |
| T10 | Prototype sample data vs the database | 93 of 94 tickers exist; sample prices and many industry labels are not real | FACT |
| T11 | Price data validity and flat-window artefacts | No invalid OHLC rows; floating residue artefacts on flat windows | FACT |

---

### 10.2 Details

#### T1. `F` vs stored Feature 04, Feature 01 and derived columns

| Check | Scope | Method | Result | Evidence |
|---|---|---|---|---|
| T1.1 All stored F04 columns that correspond to registry defaults: sma_20, sma_50, ema_12/26/50/200, rsi_14, macd, macd_signal, macd_histogram, atr_14, adx_14, bb_upper/middle/lower_20 | **Universe**: 844 equity tickers, 114,544 F04 rows (2026-04-01..2026-10-27). Full history on 7 more tickers. | `F` run on full price history (1,330,722 bars) and compared row by row with F04 version `feature04-v3-smi14-5-5-th40-talib0.6.8-c0.6.4` | Same first valid bar. 0 null mismatches. Max relative difference 1.25e-15 (adx_14, PSAB 2026-10-07). This is 1-2 ulps from the Railway incremental worker. | `evidence/verify_matrix_a/v_market.txt`; `audit/verify_matrix_a.json` a-F04-stored-identical. The auditor's 8.4e-16 bound on 6 tickers (`evidence/matrix_a/f04_vs_ts.txt`) is superseded. |
| T1.2 The same 15 columns on the latest date | 828 equity rows on 2026-10-27 | Same comparison | Max rel 1.16e-15; no null mismatch. Bit-identical except rsi_14 (556 of 828 exact) and adx_14 (500 of 828 exact), which differ in the last unit. ema_200 has 820 values (8 short histories null in both). | `evidence/benchmark/results/f04_parity.json` (script `evidence/benchmark/scripts/f04_parity.mts`) |
| T1.3 ATR | 26 tickers / 39,092 bars (auditor); 18 tickers / 27,971 bars (verifier) | `F.atr` vs `atr_14` and vs `talib.ATR(14)` | max rel 0, first valid bar 14, 0 null mismatches | `evidence/matrix_b/compare_summary_26tickers.txt`; `evidence/verify_matrix_b/compare_report.txt` |
| T1.4 Indicators derived from F04 columns: %B (I28), bandwidth (I29), NATR (I31) | 26 tickers (auditor); 18 tickers (verifier) | SQL-style derivation vs `F` | %B max rel 0 (36,723 bars); BBW 3.1e-16 (38,962); NATR 2.8e-16 (39,092); null patterns equal. On flat windows the denominator must be wrapped in `NULLIF(...,0)`, because `F` returns null when upper = lower. | `evidence/matrix_b/compare_summary_26tickers.txt`; `audit/verify_feature04.json` row correction for %B/BBW |
| T1.5 StdDev (I32) = (bb_upper_20 − bb_middle_20)/2 | BBCA, PBID, BNBR vs TA-Lib; 26 tickers vs `F` | Derivation vs `talib.STDDEV` and vs `F` | rel ≤ 1.2e-14, except flat BNBR windows where cancellation gives up to 1.3e-9 relative (about 1e-12 absolute; 80 bars) | `evidence/verify_feature04/derive_check.out`; `evidence/matrix_b/compare_summary_26tickers.txt` |
| T1.6 PPO line (I25) = 100·(ema_12 − ema_26)/ema_26 | BBCA, PBID, BNBR | Derivation vs `talib.PPO(matype=1)` | rel ≤ 2.4e-16. Signal and histogram need a recursive EMA, so they are not derivable in SQL. | `evidence/verify_feature04/derive_check.out`; `evidence/matrix_a/ppo_f04.txt` |
| T1.7 Coverage count at registry defaults | All 53 registry keys | Registry defaults vs F04 columns, with derivation checks | **Corrected by the verifier.** 9 of 53 fully served: sma, macd (3 outputs), rsi, bollinger, atr, %B, bandwidth, natr, stddev. 2 partly served: adx (adx output only; +DI and −DI missing), ppo (line only). 42 not served. F04 also stores sma(50) and ema(12, 26, 50, 200) at non-default lengths, source close only. | `audit/verify_feature04.json` F04-17 (refuted the auditor's "8 of 53, no custom parameters"); `evidence/verify_feature04/registry_list.txt` |
| T1.8 Feature 01 equalities | volume_avg_20d and volume_ratio_20d: 4 tickers (auditor), 18 tickers (verifier). return_5/20/60d: BBRI, BLTA, GOTO full history. | Column vs `F` | `volume_avg_20d` = `volume_sma(20)` (max rel 3.2e-12). `volume_ratio_20d` = `rvol(20)`, current bar included (1.5e-11). `return_{5,20,60}d_pct` = `F.roc` exactly (max abs 0, 0 null mismatches). | `evidence/matrix_b/f01cmp_report.txt`; `audit/verify_matrix_b.json` b-I35-I37-f01-identical; `evidence/verify_matrix_a/v_f01.txt` |
| T1.9 Feature 01 volatility vs I33 HV | 20 tickers, 28,319 bars | `volatility_20d_ann_pct` vs `F.hist_vol` | **Different formula** (sample stdev of simple returns vs population stdev of log returns). Per-ticker median diff 2.4-3.4% (overall 2.76%), p95 6.9%, max 23.2% (ACST). | `evidence/verify_matrix_b/hv_vs_f01.txt` (refutes the auditor's "median 0.25-3%, max 14%") |
| T1.10 IHSG location | Feature 04 tables | Row counts | IHSG has 0 rows in `Feature_04_Technical_Indicator` and 2,127 rows (2018-01-02..2026-10-27, same version) in `Feature_04_Technical_Indicator_INDEX` | `audit/verify_matrix_a.json` additional findings; `audit/feature04.md` section 5 |

**Condition for T1 (FACT).** The equalities hold only when `F` runs from the ticker's first price row, as Feature 04 does. If only the last 260 bars are recomputed, last-bar ema_200 is 0.13-1.35% off; with 500 bars it is still 0.1-0.19% off (`evidence/verify_feature04/derive_check.out`; `audit/verify_feature04.json` row correction "Matrix rows sma/ema/macd/rsi/atr/adx").

#### T2. `F` vs TA-Lib 0.6.8 / C 0.6.4

| Check | Scope | Result | Evidence |
|---|---|---|---|
| I01-I27 at defaults | 6 tickers (auditor) + 7 new tickers including flat BLTA, 75-bar PRDL and zero-volume ASPR (verifier) | 19 equal with rel ≤ 3.6e-16 (≤ 3.1e-16 on the new tickers): SMA, EMA, WMA, KAMA, ADX/PLUS_DI/MINUS_DI, AROON, MAX/MIN, SAR, RSI, STOCH, WILLR, ROC, MOM, CCI, TRIX, ULTOSC, PPO (matype 1 + EMA signal), BOP, BBANDS. Some need 2-3 TA-Lib calls (PPO + EMA; MAX + MIN; ADX + DI). No TA-Lib function exists for HMA, Supertrend, Keltner, TSI or AO; HMA, Keltner and AO built from TA-Lib pieces match within 1e-11. | `evidence/matrix_a/talib_vs_ts.txt`; `evidence/verify_matrix_a/v_talib.txt`, `evidence/verify_matrix_a/v_talib2.txt` |
| TA-Lib functions with another convention | Same | `talib.MACD` / `MACDEXT`: first bar 33 instead of 25, up to 150% relative off in warm-up (ASII), never converging on 75-bar PRDL; the EMA(12) − EMA(26) build with signal `EMA(macd[25:], 9)` is equal (rel 0). `STOCHRSI` fastk is unsmoothed: the terminal K equals TA-Lib's fastd, and D = SMA(K, 3), both rel 0; raw fastk differs by up to 66.7 points. `talib.CMO` is Wilder-smoothed: median diff 8.6-12.6 points (27 on PRDL); the plain-sum build matches within 1.2e-14. `talib.PPO` default matype 0 differs. | `audit/verify_matrix_a.json` a-I06-macd-talib, I06 row corrections, a-I14-stochrsi-k, a-I20-cmo-talib, a-I25-ppo-matype |
| I28-I53 at defaults | 26 tickers (auditor); 18 tickers (verifier) | Every TA-Lib-backed row equal, rel 0 (BBW 3e-16), same first valid bar: BBANDS-derived %B/BBW, ATR, NATR, STDDEV, SMA(V), EMA(V), PPO(V, matype 1) + EMA(9), OBV, AD, ADOSC(3,10), MFI(14). EMA and WMA Bollinger bases equal BBANDS matype 1/2. One convention gap: I39 Volume ROC is null where V[t−n] = 0, while TA-Lib gives 0 (3 bars: AYAM, AADI, CHEK). | `evidence/matrix_b/compare_summary_26tickers.txt`; `evidence/verify_matrix_b/compare_report.txt` |

#### T3. The prototype's engines vs `F`

| Check | Scope | Result | Evidence |
|---|---|---|---|
| `XI` (prototype lines 866-968) at defaults | BBCA, GOTO, MTDL, DADA, ADRO; full history from 2018; last 250 bars; tolerance 1e-9 × max\|F\| | **43 identical.** **10 differ:** kvo (different formula, about 99% of scale, often opposite sign); hist_vol (sample SD, constant ×1.026); rvol (default leaves the current bar out; with `include_current_bar:"true"` it equals `F` on all 2,125 MTDL bars); obv (starts at 0, not V[0]); psar (different start and reversal; direction differs on 12-104 of 250 bars); kama, stoch_rsi, cci, cmo, ultimate_osc (flat-window conventions). hma also differs at custom lengths (round vs floor of √n; length 15: 1.2e-2). | `evidence/html_model/parity_default.tsv`; custom lengths: `audit/html_model.md` §3.2 and `evidence/html_model/parity_custom.tsv`; scripts `evidence/html_model/scripts/parity.mjs`, `evidence/html_model/scripts/debug.mjs`, `evidence/html_model/scripts/debug_all.mjs`, `evidence/html_model/scripts/legrsi.mjs` |
| Legacy helper engine (prototype lines 753-777) | Same 5 tickers | RSI14, STOCH k/d, MACD, DMI adx/+DI, ATR14, BB upper, SUPERTREND direction (0 differing bars after bar 30), MFI14 and CMF20 equal `F` over the last 250 bars. OBV has a constant offset. RSI differs in long flat stretches (DADA, 45 bars in 2023-07: 48.14 vs 0). | `evidence/html_model/parity_default.tsv` LEGACY rows |
| Verifier correction | Code reading | There are **two** prototype engines, `XI` and the legacy helper set. Every Technical preset runs on the legacy set (lines 1091-1100). Prototype A/D (I44) equals `F` and TA-Lib (AD[0] = MFM0·V0), so it is **not** a difference. Code-level differences that show only in warm-up or edge cases: ATR/NATR bar-0 TR = H−L (l.890, 767); Chaikin SMA-seeded EMAs (l.960); MFI `q‖1e-9` (l.771); EOM 0 instead of null at V = 0; VWAP returns the source price when period volume is 0 (l.956); %B null where `F` gives 0.5 on residue-width bands; no zero-denominator guards for I31 and I38. | `audit/verify_matrix_a.json` additional findings; `audit/verify_matrix_b.json` b-prototype-engine-differs (refuted the auditor's A/D claim) |

Conclusion (FACT): the screener must call `F` and must not port either prototype engine.

#### T4. Tail window vs full history

| Check | Scope | Method | Result | Evidence |
|---|---|---|---|---|
| T4.1 Benchmark scenarios (a) RSI(7) < 30, (b) close > SMA(75), (c) MACD cross up within 5 | 845 tickers | Latest values on the last K bars (K = 250 / 500 / 750, or from 2023-10-01) vs full history; "differ" = rel > 1e-9 | K = 500 and 750: 0 differences, 0 flag changes. K = 250: MACD differs on 762 tickers, signal on 796 (max rel 6.8e-4), no flag flip today. From 2023-10-01 (a calendar window): XSPI (64 bars) and DEFI (240) change RSI/MACD (max rel 1.15e-2), and one flag changes. | `evidence/benchmark/results/compare.txt` (`evidence/benchmark/scripts/compare.py`) |
| T4.2 All 53 at defaults | 845 tickers | Same | K = 750: differences only for KAMA (1 ticker, BABP), EOM (3, ≤ 1.8e-7), KVO and its signal (25 / 29, ≤ 1.5e-7) and the 5 cumulative series (746-749 tickers). K = 500: plus ADX (2 tickers, 1.6e-8) and KVO (774 / 778). K = 250: the whole EMA/Wilder family differs on 588-830 tickers (max rel 9.7e-4, ADX). | `evidence/benchmark/results/compare.txt` |
| T4.3 Convergence after a cut at bar 1000 | 531 tickers with ≥ 1,500 bars | Bars after the cut until \|cut − full\| ≤ 1e-6 × max\|full\| | Median / p95 / max: EMA20 99/118/128; KAMA 105/191/**1,109** (BABP; a 1,000-bar tail still leaves BABP's latest KAMA 1.3e-3 off); MACD 159/184/199; ADX 202/234/668 (BEKS); RSI 164/191/459; StochRSI 185/456/713; TSI 180/206/510; Supertrend line 92/130/228; PSAR 23/79/288; CMO 14/14/425; UO 28/28/1,087. Window-only indicators converge at their first valid bar. | `evidence/verify_matrix_a/v_converge_max.txt` (refutes the auditor's 5-ticker ranges) |
| T4.4 Long custom lengths | 729 tickers (K = 500), 575 (K = 1,000) | Tail vs full at the latest bar, tolerance 1e-6 relative | EMA 200: K = 500 differs on 729/729 (up to 7.7%, SAPX 312.44 vs 336.37); K = 1,000 on 508/575 (6.2e-4). MACD 50/200/20: K = 1,000 differs on 566/575 (NFCX −2.85 vs −3.18); K = 500 can flip the sign. RSI 50: K = 1,000 on 0/575. ADX 50/50: K = 1,000 on 15/575. | `evidence/verify_matrix_a/v_tail_custom.txt`; `evidence/benchmark/results/longparam.json` (EMA 200 still differs on 516/532 at K = 1,500) |
| T4.5 Cumulative and derived states | 18-20 tickers × starts 2021, 2024, 2025 | Later start vs full history | OBV, PVT, A/D, NVI and PVI never settle. Last-bar relative differences reach 93% (OBV), 170% (PVT), 107% (A/D), 370% (PVI) and about 96,800% (NVI, AGRO: 0.558 vs 540.8). k-bar changes, ratios and N-bar highs are start-independent. "Level vs its SMA" is start-independent except for floating ties on flat windows (BNBR: 358 of 358 disagreements on flat-OBV windows). "Level vs its EMA" is start-dependent: EMA 20 for about 20-90 bars; EMA 255 up to 1,021 bars, and still on ANTM's last bar from a 2025 start. | `evidence/verify_matrix_b/startdep_report.txt`, `evidence/verify_matrix_b/derived_state_report.txt`; `audit/verify_matrix_b.json` b-cumulative-start-dependence |
| T4.6 Recursive I28-I53 settle times at 1e-9 × scale | 6 tickers × 3 starts | Later start vs full history | ATR 192-271, NATR 188-277, volume EMA 146-205, PVO 233-316 (signal 246-330), Chaikin 68-105, Force 59-135, KVO 418-624 (signal 440-641; never settled from 2025 on all 6) | `evidence/verify_matrix_b/startdep_report.txt` |

Conclusion (FACT): full history from the first price row is the only rule that is safe for every parameter value. Any "short tail" rule must depend on the parameters (`audit/verify_matrix_a.json` additional findings).

#### T5. VALUE, STATE and EVENT semantics on live bars

| Check | Scope | Result | Evidence |
|---|---|---|---|
| VALUE / STATE / EVENT from the shared core | BBCA, GOTO, MDLA (367 bars), PMUI (314 bars) on 2026-10-27 | BBCA RSI14 = 28.9596; "MACD crosses above signal" last on 2026-10-15, 8 sessions ago. GOTO MACD cross 2026-10-21, 4 sessions ago. PMUI Supertrend flipped up on 2026-07-31, 58 sessions ago. met / need for ALL and AT LEAST 2 computed with `entryNeed`. | `evidence/reuse/semantics.txt` (`evidence/reuse/scripts/semantics.mts`) |
| Whole-universe match counts | 845 tickers, every window | RSI(7) < 30: 183; close > SMA(75): 166; MACD cross up within 5 bars: 221; all three: 0. Counts are identical for full history and K = 250 / 500 / 750. | `evidence/benchmark/results/abc_*.metrics.json` |
| n/a handling | 845 tickers | (b) throws `INDICATOR_OUTPUT_EMPTY` for 1 ticker with < 75 bars (2 in the from-2023 window); the core refuses rather than returning false | `evidence/benchmark/results/run_all.log`; conditions.ts:107-109 |
| Donchian through `compare()` | 844 tickers | `C gt upper`, `C crosses_above upper`, `C lt lower`, `C crosses_below lower` give 0 hits. Against prior-bar bands they give 44,557 / 29,041 / 54,652 / 34,294. Not in ERRORS at the audit; recorded 2026-10-28 as ERRORS M255. | `evidence/verify_matrix_a/v_market.txt`; `evidence/matrix_a/donchian_check.txt` |
| Supertrend factor 0 | BBRI, BLTA, ASPR | At factor 0: 70 up-trend bars with the line above the close and 1,128 flips in 2,115 bars (60 at factor 3); recorded as ERRORS M257 | `evidence/verify_matrix_a/v_st0.txt` |
| Latest-bar state of the market | 828 stocks, 2026-10-27 | RSI < 30: 109; BOP exactly 0 on 76 (only 4 have H = L, so BOP is also 0 when C = O); VWMA-basis Bollinger on IHSG is all null | `evidence/verify_matrix_a/v_market.txt` |

#### T6. Feature 04 test suite

| Run | Scope | Result | Evidence |
|---|---|---|---|
| Auditor | `features/feature04/tests` on a scratch copy; venv with TA-Lib 0.6.8 / C 0.6.4 / numpy 2.3.5 | 49 passed in 1.86 s | `evidence/feature04/pytest_feature04.out` |
| Verifier | Same, independent re-run | 49 passed in 1.81 s | `evidence/verify_feature04/pytest_verify.out` |
| Excluded | `test_repair_job.py`, `test_selected_date_repair.py` | Not run: they need `scripts/repair_fixed_income_dates.py`, a database and the `websocket` package | `audit/verify_feature04.json` F04-15 |
| Environment caveat | — | The library pins match production, but the scratch venv runs Python 3.13 (cp313 wheel), while the image is `python:3.12-slim` | `audit/verify_feature04.json` row correction "Section 6 tests"; `apps/feature-04-worker/Dockerfile:1` |
| CI | `.github/workflows/` | Only `database-schema-docs.yml`; no pytest for Feature 04 in CI | FACT |
| Recorded earlier (documents, not re-run) | Incremental vs full shadow over 868 instruments with a live re-run, `changed_rows=0`; Terminal TS port vs stored F04, 23 tickers, 1,619 tests | Passed when recorded | `verification/feature04/INCREMENTAL_FINALITY.md`; `apps/edge-bff/terminal/tests/calc/PARITY.md` (2026-10-25) |

#### T7. Feature 04 live data checks

| Check | Result | Evidence |
|---|---|---|
| Health | Queue 868 DONE, generation lag 0. Column_Status 44,268 rows, all SUCCESS. State 6,076 rows (`feature04-state-v3`). Retry_Request 0. Outbox 128 SENT. Calculation_Log 11,964 SUCCESS, 1 FAILED (IHSG `REPAIR_REQUIRED`, 2026-10-23). | `evidence/verify_feature04/v01_health.out`, `evidence/verify_feature04/v03_logs.out` |
| Coverage | Equity: 844 tickers, 1,328,595 rows, 2018-01-02..2026-10-27; 384 start on 2018-01-02; median 1,802.5 rows; min 74; max 2,125; 10 under 200; 95 under 750. Bonds: 24 tickers, 60,643 rows from 2016-01-01. | `evidence/verify_feature04/v04_coverage.out` |
| F04 vs price | Count, first and last date equal for all 844 stock tickers. IHSG is the only price-only ticker. Bonds 24/24. | `evidence/verify_feature04/v04_coverage.out`, `evidence/verify_feature04/v25_bonds.out` |
| Version | A single calculation_version and a single timeframe (Daily), checked in 4 chunks totalling 1,389,238 rows | `evidence/verify_feature04/v05_versions.out`, `evidence/verify_feature04/v06_versions2.out` |
| Latest-date nulls | 828 equity rows: 0 nulls except ema_200 (8) and last_swing_high (5); temp_* nulls by design | `evidence/verify_feature04/v07_nulls.out` |
| Session gaps | **Corrected by the verifier.** Against the true session calendar (2,127 IHSG dates, equal to broker dates), 0 of 844 equity tickers are gap-free. 840 span 2026-09-17/18, which are missing for every stock because of an ingestion gap (M238, OPEN). 222 tickers miss > 5%; 9 miss > 50%; 89,968 ticker-sessions are missing in total. | `evidence/verify_feature04/v28_gaps2.out`, `evidence/verify_feature04/v21_ihsg_dates.out`, `evidence/verify_feature04/v22_gapdays.out` (refutes the auditor's "242 gap-free") |
| Split breaks | **FACT on live data** (the auditor had it as INFERENCE). PBSA 1:2 split, ex-date 2026-10-14: close 845 → 384, older history unadjusted; on 2026-10-27 F04 shows rsi_14 22.8, sma_50 706.4 vs close 302, bb_lower_20 85.7. FORU rights issue, ex-date 2026-09-22: close 2,560 → 176; bb_lower_20 negative from 2026-09-25 to 2026-10-16 (minimum −2,114). Of 13 STOCK_SPLITs since 2025, only PBSA is unadjusted. ERRORS D22 now records the mixed adjustment (OPEN, commit `641e55e`). | `evidence/verify_feature04/v15_foru.out`, `evidence/verify_feature04/v16_splitcheck.out`, `evidence/verify_feature04/v17_split_breaks.out` |

#### T8. Flow formula checks

| Check | Scope | Result | Evidence |
|---|---|---|---|
| Avg Buy = value / (lots × 100) | Auditor: 387 sample rows of `IDX_Broker_Summary`, 5 tickers. Verifier: 574 buy rows plus the sell rows of 7 tickers on 2026-10-27. | Equal; max difference 8e-13 (auditor), 8.2e-13 buy / 9.0e-13 sell (verifier). Same formula as Terminal `brokerAgg.ts:25`. | `audit/flow.md` 1; `audit/verify_flow.json` C10 |
| Price volume = Regular F05 `buy_lots` × 100 | Auditor: 5 tickers on 2026-10-27. Verifier: 10/10 on 2026-10-27 and 11/11 historical samples (2019-03-12, 2022-06-15, 2025-06-10). Also BBCA and MTDL on 2026-10-23 (BBCA 495,623,900 = 4,956,239 × 100). | Equal. BBCA all boards 457.17 M vs price 366.85 M, so the price table is Regular-board volume. | `audit/verify_flow.json` C9; `audit/html_model.md` 1.2 |
| Trade count = buy freq sum | Verifier: 865/865 latest Regular rows; 18,546/18,546 rows of October 2026 (Regular 16,392, Nego 2,068, Tunai 86) | Buy freq = sell freq on every row. 0 null frequency in 161,294 universe Regular rows in 2026. BBCA 81,369 and BBRI 60,879 on 2026-10-27. INFERENCE: reading the sum as "number of trades" is supported by the equality but not checked against an exchange count. | `audit/verify_flow.json` C8 |
| Foreign % of value = F06 `foreign_net_turnover_ratio_Nd` | 865 Regular rows, 2026-10-27 | Recomputed ratio = stored on 833/865; recomputed 20-day net = stored on 847/865. 0 mismatches among tickers with 20 sessions in the window; the differences come from ticker-session vs market-session windows. | `evidence/verify_flow/c5.sql`; `evidence/flow/q2c_check.sql` |
| Live function bodies vs migrations | `refresh_feature_02`, `refresh_feature_06` | Live F02 body = migration `20261025_008`. Live F06 body = `20261022_005:66-298`; `20261022_003` identical after renames (diff 0 of 233 lines). | `evidence/verify_flow/live_f02.sql`, `evidence/verify_flow/live_f06.sql`, `evidence/verify_flow/f06_a.sql`, `evidence/verify_flow/f06_b.sql` |
| F02 is sparse on the latest date | Window 2026-09-30..10-27 | ANTM foreign 20-day net from latest-date F02 rows: −408.05 B vs true −477.11 B; DMAS 39.09 vs 82.41 B. Combinations with a latest-date row: ANTM 79/143, BBCA 112/169, DMAS 52/94. | `audit/verify_flow.json` C3 |
| Regular vs all boards, 20-day foreign net | 841 universe stocks with any F06 row in the window (corrected from 844) | 168 differ, 59 by > 10%, 20 flip sign (CARE −1.50 B Regular vs +376.22 B all boards) | `evidence/verify_flow/c11.sql`; `audit/verify_flow.json` C11 |
| Bandar ranking rule | Code reading | Prototype `bandarRatio` (l.782-783) uses the same positives-of-top-N plus negatives-of-bottom-N rule as `flow.ts top5Accumulation` (l.108-119), with N fixed at 5 and no denominator in the Backtest | `audit/verify_flow.json` C7 |
| Foreign streak | 2026-10-27, market sessions | Max foreign net-buy streak 21; 27 tickers ≥ 5, all universe stocks | `evidence/verify_flow/streak.sql` |
| F03 breadth ratio | 865 Regular rows | `net_buy_broker_ratio` = net_buy / active brokers; on 79 rows `active_broker_count` ≠ buyers + sellers, so it is not the proposed breadth metric | `audit/verify_flow.json` row correction B5 |
| Broker profile coverage | 2026-10-27 | All 89 brokers trading that day are in `IDX_Broker_Profile` (112 rows) | `audit/verify_flow.json` confirmed list |

#### T9. ADV (close × volume) vs exact traded value

| Check | Scope | Result | Evidence |
|---|---|---|---|
| 20-session ADV vs F03 Regular `total_buy_value` | Window 2026-09-30..2026-10-27 (20 IHSG sessions), 840 stocks with ≥ 1 bar | Median ratio 1.0001 (p5 0.966, p95 1.018). Stocks ≥ Rp 1 B: 395 by close × volume, 396 by Regular value, 431 with Nego and Tunai included. 48 stocks have fewer than 20 bars. Default prototype universe (price ≥ 50 and ADV ≥ 1 B) = 353 stocks. | `evidence/fundamentals_universe/adv_dist.txt`, `evidence/fundamentals_universe/value_check.txt` |
| Absolute difference vs F06 Regular `foreign_buy_1d + domestic_buy_1d` | 1 day: 828 stocks on 2026-10-27. 20-session mean: 840 stocks. | 1 day: median 1.45%, p90 4.05%, p99 7.92%, max 14.8%. 20-session mean: median 0.67%, p90 2.57%, max 15.3%. 2 stocks land on opposite sides of the 1 B threshold. | `audit/verify_flow.json` row correction "S3 row 11 (adv) / open question 8" (replaces the auditor's "about 1-2%") |
| Prototype ADV definition | Code | `val = c × v` (l.697), `SMA(val, 20)/1e9`, equal to core `liquidity` (signals.ts:174) | `audit/reuse.md` C26 |

#### T10. Prototype sample data vs the database

| Check | Result | Evidence |
|---|---|---|
| Tickers | 94 listings; 93 in `IDX_Stock_Universe`; WIKA is in neither the universe nor the price table | `evidence/html_model/listings_check.txt`; `evidence/fundamentals_universe/proto_vs_db.txt` |
| Sectors | 92 of 93 match (SIDO: prototype Consumer Non-Cyclicals, DB Healthcare / Pharmaceuticals); all 11 prototype sector names exist in the DB | same |
| Industries | Industry matches for 43 of 93 tickers. 14 of 31 distinct prototype industry labels exist in the DB; 17 are prototype-only. The 25 mismatches in `evidence/html_model/listings_check.txt` count label pairs (prototype → DB), not distinct labels (INFERENCE from the file). | `evidence/fundamentals_universe/proto_vs_db.txt`; `evidence/html_model/listings_check.txt` |
| Sample prices | 62 of 93 sample prices differ by > 25% from the DB close of 2026-10-27 (e.g. BBCA 9,850 vs 4,900) | `evidence/html_model/listings_check.txt` |
| `Universe_Equity_Description` | Sector and Industry are swapped relative to `IDX_Stock_Universe` (BBCA Sector "Banks", Industry "Financials"). 841 of 844 rows differ; the other 3 compare equal only because both values are "Undefined". ERRORS D23 now records the swap (OPEN, commit `641e55e`). | `evidence/fundamentals_universe/ued.txt`; `audit/html_model.md` HM14 |
| Synthetic look-ahead | The prototype's foreign flow uses the next 3 sessions' returns (l.699-700) | prototype code |

#### T11. Price data validity and flat-window artefacts

| Check | Result | Evidence |
|---|---|---|
| Validity | 1,330,722 rows, all Daily and final, 845 tickers. 0 rows break Feature 04's OHLC rule. 123,853 rows have H = L. 40 rows have zero volume, 21 of them on the ticker's first bar. Volume is NULL on 2,127 rows, all IHSG. 150,797 rows across 181 tickers have non-integer OHLC (split-adjusted history). | `audit/verify_matrix_a.json` a-price-data-valid; `audit/verify_matrix_b.json` I39 row correction |
| Flat-window residue | UO is outside [0, 100] on 2,972 bars. 3,218 of 31,764 fully flat 28-bar windows give UO ≠ 0. 3,299 of 41,412 flat 20-close windows give Bollinger upper > basis. CMO is non-null on 3,231 of 44,033 flat 14-change windows (17 tickers). No such artefact is on the 2026-10-27 bar. | `evidence/verify_matrix_a/v_flat.txt` |
| %B / ADR residue | In F04's last year: 502 equity ticker-days on 16 tickers have zero width (%B null). 100 equity ticker-days (BABP 59, BCAP 41, both flat at 50) have a residue width, and `F` %B is 0.5 there. The other 54 of the auditor's 154 rows are bonds. ADR is negative on 905 BNBR bars, and > 0 on 274 BABP bars whose true range is 0. | `audit/verify_matrix_b.json` b-flat-window-fp (refutes the auditor) |
| Stale RSI on flat stocks | Wilder RSI keeps its last value through flat stretches (37,100 of 44,033 flat 14-change windows have RSI ≠ 0, as in TA-Lib), so "RSI < 30" can match a flat or suspended stock on an old value | `audit/verify_matrix_a.json` I13 row correction and additional findings |

---

### 10.3 What was NOT tested

| Area | Not tested | Label |
|---|---|---|
| End to end | No screener exists, so nothing in the chain was tested: HTML request → edge-bff → screen execution → Feature 04 / precomputed path and custom path → response → rendered result → preview → Send to Backtest. | FACT |
| Condition engine | No automated tests of `between`, per-condition "within N", ALL / ANY / AT LEAST, near miss, event date or sessions ago. Only demonstration scripts exist (`evidence/reuse/scripts/semantics.mts`, benchmark scenario c). The new operators (between, lagged, cross-instance, indicator of an indicator) do not exist yet. | FACT |
| Data dates | The rule for result date, event date and source data-through was not tested. No as-of or staleness policy exists to test (16 stale tickers; the 2026-09-17/18 ingestion gap). | FACT |
| Universe logic | Sector, industry, price and ADV filters were counted, not tested as filter code. Index, board, notation, free float and market cap cannot be tested: there is no data. | FACT |
| Existing suites | Not re-run in this audit: backtest-worker tests (`apps/backtest-worker/tests`), Backtest page tests (`apps/edge-bff/backtest/tests`), edge-bff pytest (needs a disposable Postgres), terminal calc parity (`apps/edge-bff/terminal/tests/calc`). Last recorded on `main` by EXEC-BACKTEST-LOAD (2026-10-27): terminal-api 31, backtest-worker 186, Backtest page vitest 88 plus the smoke run, Terminal vitest 690 passed; edge-bff 225 passed with 1 pre-existing failure and a flaky Chromium test (ERRORS M254, OPEN) (`ERRORS_AND_SOLUTIONS.md` EXEC-BACKTEST-LOAD, Bukti). Not re-verified here: their pass state at `010af1e` is UNKNOWN (check: run each suite). | FACT (recorded) / UNKNOWN |
| Feature 04 | The 2 database-bound repair test files. The repair path (`backfill.py` + `bootstrap_states.py`) was not executed; its abort at IHSG is INFERENCE from code, with a dry-run nuance noted by the verifier (ERRORS D27). | FACT / INFERENCE |
| Planned price refill | The planned refill of 2026-09-17/18 prices (EXEC.md about l.7999, item F3) was not run. From code, about 840 equity tickers would end `REPAIR_REQUIRED` (`audit/verify_feature04.json` additional findings; ERRORS D26). | INFERENCE |
| Published files and quotas | No terminal-api or edge-bff call was made. Published manifest pack bytes were not read; packs were rebuilt with the publisher's encoding instead. Live quota rows were unreadable (pgweb is denied on schema `terminal`). | FACT |
| Flow references | The bandar ratio, bandar average price, frequency spike and breadth metrics were computed (Q3, Q7) but cannot be validated: no approved formula or external reference exists. Whether Stockbit's or IDX's public foreign net uses the Regular board or all boards was not checked (no external call). The M157 source-gap re-check hit the 30 s timeout. | FACT / UNKNOWN |
| Dividends | Sample trailing yields (e.g. BBCA 7.78%, UNVR 14.41%) were not validated against an independent source. Amounts are not split-adjusted (`dividend_value_adjusted` = 0). | FACT |
| Fundamentals | Nothing to test: no fundamental data exists. | FACT |
| Performance under load | Concurrency, cache hit ratio, bytes from terminal-display, Railway-internal latency and memory under real requests were not measured (see PERFORMANCE EVIDENCE). | FACT |
| Screen Performance History | Not implemented in the prototype beyond stock vs IHSG rebased (prototype l.1575-1588); nothing to test. | FACT |
| Browser | CSP behaviour of a screener sub-app, IndexedDB under 845 packs, accessibility fixes and the theme hand-off were not tested. | FACT |
| Decisions, not tests | KVO definition (three disagreeing definitions, P16), I37 RVOL semantics (P6), the VWAP Session anchor (P17), the HV naming against Feature 01 (P18), and the flat-window epsilon guard (P19) needed user decisions before tests could be written. All five were decided with the go of 2026-10-28 as recommended (`F`'s classic Klinger; `include_current_bar` hidden, RVOL with the current bar; Week to Year anchors only; "Historical volatility (log, population)"; raw doubles), so their tests follow TEST PLAN. | FACT |


## TEST PLAN

Approval item 14. Every test below is **PROPOSED**; what has already been measured is in TEST EVIDENCE. FACT: no CI runs these suites (the only workflow is `.github/workflows/database-schema-docs.yml`), so each family is run by hand before every merge and its output is recorded (AGENTS.md: evidence by file, log or run ID). That is TEMPORARY, paired with the optional CI workflow of CHANGES AWAITING APPROVAL A9 (RISKS / TRADE-OFFS R7). Labels and evidence notation as in TARGET ARCHITECTURE.

Each family names what it proves, where it lives, its data and its pass criterion. A rule that generalises an observed defect is tested on at least two further cases where it applies ("Applies beyond the observed case") and on one where it must not apply ("Must not apply"), the user's standing rule.

### 10b.1 Formula parity

| Test | Where | Data | Pass criterion | Applies beyond the observed case | Must not apply |
|---|---|---|---|---|---|
| Existing Terminal calc parity stays green | `apps/edge-bff/terminal/tests/calc` (vitest) | Its fixtures | All green, unchanged count | — | — |
| Snapshot vs Feature 04, registry-default columns | `scripts/screener/parity_f04.py`; record `verification/screener/F04_PARITY.md` | All equity tickers at a common date: snapshot from the rack; Feature 04 read-only (pgweb now; the optional `f04` file in Phase 2) | `sma_20`, the 3 MACD columns, `rsi_14`, the 3 Bollinger columns, `atr_14`, `adx_14`, plus 5 derivations (%B, bandwidth, NATR, stddev, PPO line, `NULLIF(...,0)` denominators): relative difference ≤ 1e-12 and identical nulls. FACT today: 1.16e-15 on 828 rows | Flat-window tickers (BNBR, BABP, BCAP) | A perturbed fixture (one bar changed) must fail |
| Snapshot vs Feature 01 | same script | I35, I37, I17 vs `volume_avg_20d`, `volume_ratio_20d`, `return_{5,20,60}d_pct` | Equal within 1e-9 relative, identical nulls | — | I33 asserted **different** (documented: sample vs population, simple vs log returns) |
| `F` on typed views ≡ plain arrays | `apps/screener-worker/tests/typed_views.test.ts` | 53 indicators × 50 tickers (deterministic sample incl. short histories) | Bit-identical outputs, else the shared-memory path stays off | Tickers with 74 bars (RANS) and with flat windows | — |

### 10b.2 Precomputed vs dynamic

| Test | Where | Data | Pass criterion |
|---|---|---|---|
| Explicit defaults hit the snapshot | `apps/edge-bff/screener/tests/core/metrics.test.ts` | Fixture universe | For all 53, explicit default parameters give the same key and bit-identical tails |
| Dynamic equals a direct call | same | Fixture + live sample | RSI(7) through `series()` equals `F.rsi` with length 7, bit for bit; a custom length above the default cap is refused with `PARAM_OUT_OF_RANGE` |
| Dynamic path vs Feature 04 at its stored non-default configurations (the brief's "precomputed vs dynamic") | `scripts/screener/parity_f04.py` | All equity tickers at a common date; `series()` called with explicit custom parameters on an empty LRU, pre-warm off: I01 length 50 vs `sma_50`; I02 lengths 12, 26, 50 and 200 vs `ema_12`, `ema_26`, `ema_50`, `ema_200` | Relative difference ≤ 1e-12 and identical nulls; each cell reports `source:"dynamic"`, `is_default:false` |
| Tail evaluation equals full evaluation | `metrics.test.ts` | Fixture | For every bar of the `SCREENER_WITHIN_MAX` + 1 bar tail, VALUE/STATE/EVENT on the tail equal the same test on the full series |
| History class | `tests/core/contract.test.ts` | Cut at bar 1000 | Window class equal; recursive and cumulative unequal (proves the "full history" rule is still needed) |

### 10b.3 Condition parity

| Test | Where | Pass criterion | Applies beyond the observed case | Must not apply |
|---|---|---|---|---|
| gt, lt, crosses vs Backtest | `tests/core/evaluate.test.ts` | Equal to the Backtest's `conditionSeries[at]` on 200 tickers for registry conditions | Every output pair of the 8 "pair" indicators | — |
| `between` | same | Inclusive at value = min and = max; `value > value2` refused with `INVALID_CONDITION` field `value2` | Negative ranges | `value = value2` is accepted |
| `within` boundaries | same | Event N−1 bars ago passes; N bars ago fails; `bars_ago` and `event_date` exact | N = 1 and N = `SCREENER_WITHIN_MAX` | N = `SCREENER_WITHIN_MAX` + 1 is refused |
| Edge bars | same | Bar 0 never true; NaN false; missing previous bar false | A ticker whose first valid bar is the evaluation bar | — |
| State ≠ event | same | A state true for 10 bars with no cross inside N fails the event | Pattern events (`breakout`, `volspike`) | — |
| Same-bar comparison lag (probe, TARGET ARCHITECTURE §6.8) | same + `build-screener-registry.mjs --check` | Donchian prior-band test ≡ core `breakout`; the same-bar form is never offered | Donchian lower band (breakdown ≡ close < prior lowest low); `close > rolling_max(high, 250)` as a transform gets lag 1 | Bollinger and Keltner upper stay at lag 0 (`close > upper` does occur on the fixture) |
| NA reason codes | same | Every code produced with its reason: RANS (74 bars) → `INSUFFICIENT_HISTORY`; IHSG volume → `NULL_AT_EVALUATION`. A stale ticker is never NA: it is evaluated at its own last bar and carries the row remark `STALE` | A zero-width Bollinger window (BNBR); a VWMA-basis I27 cell on IHSG → `NULL_AT_EVALUATION` with the volume reason | The same I27 cell with an SMA basis on IHSG has a value |
| Operator mapping (TARGET ARCHITECTURE §6.9.1) | `tests/core/mapping.test.ts` | Each compound operator equals the prototype rule on fixtures: `kxd_os`, `hup`, `zero`, `squeeze`, `obv high`, `price_ma rising` (21 bars) vs the line shape's `rising` (5 bars) | ANY and AT LEAST count a compound operator once | — |

### 10b.4 Data dates and refresh

| Test | Where | Pass criterion | Applies beyond the observed case | Must not apply |
|---|---|---|---|---|
| Evaluation date | `apps/screener-worker/tests/snapshot.test.ts` | E = `price_through`; every response carries `price_through`, `published_at` | — | — |
| Stale tickers (P4, decided) | same | A ticker whose last bar is before E is hidden by default (chip "Traded on `E`", which names how many it hides); with the chip off it is listed, evaluated at its own last bar, with the row remark `STALE` and its last bar date in the run answer, the preview and the CSV | ADHI (last bar 2026-08-21); a ticker suspended in the middle of a `within` window | A ticker whose last bar = E is not stale and carries no remark |
| Missing sessions | `tests/core/evaluate.test.ts` | Across 2026-09-17/18, `bars_ago` counts the ticker's bars and `market_sessions_ago` the IHSG calendar; both reported | A synthetic gap on another date | — |
| Flow lag | `tests/core/flowmetrics.test.ts` (Phase 2) | `flow_through` < `price_through` by more than the maximum → `FLOW_LAGGED`; within it, cells carry the flow `eval_date` | — | A lag of exactly the maximum passes |
| Refresh integrity | `apps/screener-worker/tests/refresh.test.ts` | Corrupted sha256 or size → swap aborted, previous version keeps serving, `REFRESH_FAILED` logged; cross-check mismatch (last bar or rows vs `/manifest`) → aborted; a price ticker missing from the reference file → aborted | A truncated download; a missing index entry; an indexed `bytes` above `SCREENER_MAX_FILE_BYTES` → refused before any grant; an inflated document above `SCREENER_MAX_INFLATED_BYTES`, or a refresh above `SCREENER_MAX_REFRESH_BYTES` → aborted | A file already in the disk cache by sha256 is read without a grant (a restart grants nothing) |
| Version stability | same | Reload of identical data keeps `price_data`; one changed bar changes it | — | — |
| Price breaks (derived rule, TEMPORARY; TARGET ARCHITECTURE §6.12) | `tests/core/universe.test.ts`, `evaluate.test.ts` | A price-affecting action with `ADJUSTED_HISTORY_BOUNDARY` ≤ ex-date ≤ the ticker's last bar flags the ticker; the count of flagged tickers is derived (8 on the 2026-10-27 data, live L6). A flagged ticker is hidden by default (chip "No unadjusted price break"); with the chip off it is listed with the row remark `PRICE_BREAK` (action, ex-date, ratios, observed close ratio). Under P4.1 (A) every price-derived cell keeps its value and its pass or fail, and a cell whose lookback contains the ex-date carries the cell remark `PRICE_BREAK_IN_LOOKBACK` (P4 and P4.1 A, decided 2026-10-28) | PBSA (split, ex 2026-10-14) and FORU, ENRG (rights, ex 2026-09-22 and 2026-10-05): `rsi_14`, `sma_50` and recursive or cumulative cells are marked; an SMA(20) cell whose window has moved past the ex-date carries no remark | RAJA (split 2026-07-16, before the boundary, adjusted 920 → 875); MGLV (ex-date 2026-11-02, after its last bar); a cash dividend; a flow cell and ADV20 on PBSA carry no cell remark; no value is blanked |

### 10b.5 Universe logic

| Test | Where | Pass criterion | Applies beyond the observed case | Must not apply |
|---|---|---|---|---|
| Sector and industry source | `tests/core/universe.test.ts`; publisher test | Values only from the reference file `ref/tickers.json.gz` built from `IDX_Stock_Universe`, grouped by `groupingsOf`; a fixture with swapped columns (the D23 shape) in another table never leaks | — | — |
| Unclassified stocks (P15) | same | XCID, XCIS and XSPI are counted apart as unclassified, never as an `Undefined` value; an include filter keeps them only with `include_unclassified`; an exclude filter keeps them | A fixture stock with an empty industry and a sector | BBCA is counted under Financials; IHSG is never counted (an index) |
| ADV | same | ADV20 ≡ `signals.ts liquidity()` at E | A ticker with fewer than 20 bars | — |
| Price, traded, history length | same | Boundaries inclusive as documented | — | — |
| IHSG | same | Never in the stock universe; available as the `vs_index` reference | — | — |
| Board, index, market cap, free float, notation (no data) | `tests/core/universe.test.ts`, `validate.test.ts` | A definition that uses any of them is refused with 422 `METRIC_UNAVAILABLE {metric, availability:"REQUIRES_DATA", reason}`; every row carries `board:null`, `market_cap:null`; the notation filter defaults off and is never a silent no-op | Each of the five filters | — |
| Page = worker | `apps/edge-bff/screener/tests/page/universe.test.ts` | `universe.ts` in the page and the worker's S0 give the same counts on the same `/universe` rows | — | — |
| Hidden tickers and the rank population (P4, P7) | `tests/core/universe.test.ts`, `xsection.test.ts` | `/universe` lists every stock, hidden ones included, with their remarks; each chip's count equals the tickers it hides; turning a chip off changes no other ticker's `rs_rank` and no preset count (both fixed on the default universe); a shown ticker is ranked against that population | A ticker both stale and flagged carries both remarks | With both chips on, no row carries a `STALE` or `PRICE_BREAK` remark |
| Orphan flow tickers | worker refresh test (Phase 2) | Flow rows whose ticker is not in the reference file are counted in the refresh log (`orphans`), and no ticker name appears in code | A fixture with two such tickers | A ticker in the reference file is never counted |

### 10b.6 Match logic and planner

| Test | Where | Pass criterion |
|---|---|---|
| ALL, ANY, AT LEAST | `tests/core/match.test.ts` | `need` = `entryNeed`; `met` counts PASS only; n = 1; `at_least` > n means all |
| One near rule | same + page test + CSV test | `near = !match && need ≥ 2 && met == need − 1` identical in run, preview pill and CSV |
| Planner property test | `tests/core/plan.test.ts` | Random definitions (ALL, ANY, AT LEAST; 1-20 conditions mixing precomputed, dynamic and cross-sectional; many seeds): pruned output = exhaustive output for match set, near set, every displayed cell, `met`, `na_count` |
| Per-condition counts | same + page test | A condition marked `exhaustive` has the exhaustive run's `passed`; a non-exhaustive condition is never rendered against U (the card shows "m of n evaluated") |
| Stage order | same | Permuting S3 order changes no result |
| Budget | same | A definition costed above `SCREENER_MAX_CPU_MS` is refused with `LIMIT_EXCEEDED {limit:'compute_budget', costliest}` before any compute |

### 10b.7 Flow (Phase 2)

| Test | Where | Pass criterion | Must not apply |
|---|---|---|---|
| Self-check | worker refresh | Recomputed 5/10/20/40/60-day sums and 1/5/20-day ratios equal stored F06 where the ticker has the sessions; otherwise flow cells NA `DATA_INTEGRITY` | A short-history ticker (fewer sessions than the window) is not flagged |
| Top-N | `tests/core/flowmetrics.test.ts` | `topNAccumulation(5)` ≡ `top5Accumulation` bitwise; a second test pins `flow.ts`'s content hash, so a change there fails until the TEMPORARY copy is reviewed (TARGET ARCHITECTURE §6.11) | — |
| Backtest parity | same, with published broker files for sample tickers | All-board `fnet` and `broker` equal the Backtest's `flowCondition` | — |
| Completeness gate | `apps/terminal-publisher/tests/test_publisher.py` | A date whose F06 Regular count is below the F05 Regular ticker count is excluded (a mid-round partial date); a Nego-only partial date is also excluded | A weekend date with 0 = 0 rows is skipped as no session, not as partial; a complete date (865 = 865, live L5) is kept |
| Board (P8 b, decided: all boards by default) | `flowmetrics.test.ts` | A flow reference without `board` is evaluated on all boards; all-board windows and non-additive fields (% of value, buy days, z-scores, strength, frequency ratios) are recomputed from the summed one-day components, never by adding stored per-board fields (fixture: a Nego row absent on the evaluation date); Regular and all-board variants differ where the data differ (fixture with Nego flow) | A Regular-only ticker gives equal variants |
| Dividend basis (P11) | `tests/core/metrics.test.ts` | A TTM window with a price-affecting action gives NA `MIXED_ADJUSTMENT_BASIS` or the rescaled value, per the P11 rule (PBSA) | A ticker without such an action is unchanged |

### 10b.8 Send to Backtest (Phase 1b)

| Test | Where | Pass criterion |
|---|---|---|
| Losslessness | `tests/core/to-backtest.test.ts` | For every lossless kind, `evaluate(...)[at]` = Backtest `conditionSeries(calc, toBacktest(c))[at]` at every bar on fixtures |
| Round trip | same | Definition → handoff → `definition` byte-identical under `canonicalJson`; every left-out condition is recoverable from `left_out[].condition`; the cards pass Backtest core validation |
| Lossy list | same | `between`, mixed `within`, Regular flow, top-N ≠ 5 are in `left_out` with reasons |
| Limits from the Backtest | same | `to-backtest.ts` takes the catalog `limits`: with the live values, more than `max_portfolio_tickers` (12) preselects that many by sort; a catalog fixture with `max_portfolio_tickers` 5 and `window_bars.max` 10 changes the preselection and the lossless/lossy split; more enabled cards than `max_conditions` go to `left_out`; the wire never exceeds a limit |
| Import | `apps/edge-bff/backtest/tests/import.test.ts` | Key read once and deleted; invalid handoff refused with a toast; per-ticker sha mismatch shows the version note; `definition` kept beside the cards |
| Import with an early and a delayed catalog | Backtest smoke (the EXEC-BACKTEST-LOAD stub already delays) | Early catalog (within `QUICK_MS`): the import is applied in `boot()`. Delayed catalog: the page draws on `PROVISIONAL`, the import is validated against the arrived catalog and applied in `catalogArrived()`, and a later redraw keeps it (it counts as an edit). The page stays responsive throughout (M253) |
| Navigation | `apps/edge-bff/tests/test_screener.py` (Chromium) | Frame → shell → Backtest frame; a message from another origin or another frame is ignored |

### 10b.9 Isolation (Backtest and Feature 04 untouched)

| Test | Where | Pass criterion |
|---|---|---|
| Tripwire | `scripts/screener/check_backtest_untouched.mjs` | `engineVersion()` and `REGISTRY_VERSION` equal those of `origin/main`; no diff under the must-not-change paths |
| Backtest worker | `apps/backtest-worker` `npm test`, `npm run registry:check` | Green |
| Backtest page | `apps/edge-bff/backtest` vitest, smoke, visual 1:1 | Green, 0 visual difference |
| edge-bff suite | `apps/edge-bff/tests` | No new failure. FACT: the baseline already holds the two Chromium failures of ERRORS M254 (OPEN), which are not counted against this work |
| Feature 04 | `features/feature04/tests` (pinned venv) | 49 passed (FACT today: 49 passed, `audit/feature04.md` §6) |
| Load isolation | Phase 17 | A Backtest job's duration is unchanged while screens run |

### 10b.10 Contract drift

| Test | Where | Pass criterion | Must not apply |
|---|---|---|---|
| Generated registry | `build-screener-registry.mjs --check` | No diff; every probe-derived field is re-derived and compared | — |
| Start-up check | worker | Refuses to start on a hash mismatch (and runs the backtest worker's registry check) | — |
| Overlay coverage | `tests/core/contract.test.ts` | One overlay entry per base id and vice versa | — |
| Narrow-only | same | No overlay or derived range is wider than the base | — |
| Narrowing probes (TARGET ARCHITECTURE §6.8) | same | Refused: I19 constant 0 and I50 initial_value 0 (degeneracy probe), I11 multiplier 0 (collapsed bands), I09 factor 0 (override, checked against the probe it overrides), `annualization_periods` 252.5 (floor probe) | Accepted: an I23 weight of 0 (a valid minimum); length 20; `annualization_periods` 252 |
| `not_accepted` rule | same | Every parameter with reason "not read by the calculation module" is hidden and its value never shown (I34 `timeframe`, I37 `reference_method`, I37 `include_current_bar`) | A parameter `F` reads (I37 `length`) stays |
| Inputs per source | same | The poison probe gives `inputs` that follow the chosen source (I28, I29, I32, I33 with source `hl2` list H and L) | A source-free indicator (I40 OBV) keeps C and V |
| Operator coverage | `tests/core/mapping.test.ts` | Every (key, op) pair of `evidence/html_ui/catalog.json` maps to a wire form or carries a disabled reason (TARGET ARCHITECTURE §6.9.1); an unmapped pair fails the test | — |
| Derived availability | `tests/core/metrics.test.ts` | Removing `flow_f06` from a fixture index turns every flow metric `REQUIRES_DATA` with no code change; a fixture file family becomes AVAILABLE by adding `screener-metrics.json` entries only | Technical metrics stay AVAILABLE when the flow file is removed |
| Oracle columns | Python test beside `parity_f04.py` | Every oracle column read from `scripts/terminal_indicator_spec.py --json` exists in `features/feature04/engine.py` `COLUMNS`; `terminal_indicator_spec.py --check` stays green (the applied migration `20261025_102` unchanged) | — |
| Parity record | `verification/screener/F04_PARITY.md` | Pinned `registry_version` + Feature 04 VERSION; a change to either requires a re-run | — |

### 10b.11 API, security and refusals

| Test | Where | Pass criterion |
|---|---|---|
| Auth and CSRF | `apps/edge-bff/tests/test_screener.py` (disposable Postgres, `EDGE_TEST_POSTGRES_URL`) | Every write route refuses a missing Origin or CSRF token; reads need a session. A test walks `app.routes` and fails on any POST, PUT, PATCH or DELETE route without `write`, derived from the route table (the class of ERRORS M259) |
| Input guards | same | Body > 131,072 B → 413; NaN, Infinity, 1e400, lone surrogate → 422 `INVALID_INPUT` |
| Relay mapping | same | Worker 4xx relayed after `error_of` + `public_data`; worker 504 → 504; other → 503 `SCREENER_UNAVAILABLE`; no internal host or key in any answer |
| Latest wins | same | A newer `client_order` of the same (owner, page) ends the older call with 409 `SCREEN_REPLACED`; a call of another page of the same owner is not cancelled (MULTI-USER SCALE AND COST 6d.6) |
| Shared answers carry no owner data | worker + edge-bff | Computed fresh for two owners, the run answers for one definition are identical apart from `timings_ms`; a cache hit returns the first computation's bytes (6d.2) |
| Version pinning and grace window | worker | A `run` or `counts` pinned to the previous `price_data` is served during `SCREENER_PREVIOUS_GRACE_S` and refused with 409 `DATA_VERSION_CHANGED` after it; a newer version not yet loaded answers `DATA_VERSION_PENDING`, which edge-bff retries once and turns into 503 `SCREENER_NOT_READY` with `Retry-After: 2`; a refresh whose index names the same files keeps the snapshot (6d.2, 6d.4) |
| Owner lanes | worker | With one owner tag looping costly screens, another tag's screens start within one round-robin turn; no more than `SCREENER_OWNER_INFLIGHT` run per tag (6d.6) |
| Catalog cache monotonic | edge-bff | A `/health` answer from a replica that has not swapped never replaces a newer catalog; a worker answer at a newer `price_data` drops the cached catalog and universe at once (6d.5; PAGE LOAD SEQUENCE 6c.5) |
| Owner filter and limits | same | Every store statement filters `owner_key`; `SCREEN_LIMIT`, `WATCHLIST_LIMIT` → 422; stale `revision` → 409 |
| Migration | same (`test_the_migration_refuses_*` pattern) | `$preflight$` refuses a second run; `$verify$` holds; provisioning refuses unexpected reach |
| Refusal messages and limits | worker + edge-bff | Every refusal code names the field (where there is one) and the fix; every catalog `limits[]` entry carries its value, rule and one right and one wrong example, generated from the value; the catalog values equal the environment values (AGENTS.md gate rule) |
| terminal-api `/xsection` | `apps/terminal-api/tests/test_api.py` | Refuses a caller without the proxy key, a direct subscriber's session included; writes one audit row under `REF` with `dataset='xsection'` and counts the files and bytes; an unknown name is refused with the indexed list |
| terminal-api `/state` | same | The existing tests stay unchanged (`test_state_names_the_publication_without_quota_or_audit`, `test_state_unreadable_is_503`); `test_bucket_state_keeps_the_last_read_publication` gains `xsection`; `/state` returns `xsection` when `state.json` holds it and still answers the backtest worker's `publication()` |
| Publisher | `apps/terminal-publisher/tests/test_publisher.py` | Each ticker's slice equals its pack document; the index is written before `state.json`; other modes carry the index forward; pruning keeps the previous index's objects |
| edge-bff suite | `apps/edge-bff/tests` | Pass = no new failure against a baseline that includes the two M254 failures |

### 10b.12 Page

| Test | Where | Pass criterion |
|---|---|---|
| Bundle | `apps/edge-bff/screener/tests/bundle.test.mjs` | Production bundle has no `indicators.ts`, `conditions.ts` or fixture code; one IIFE script, no inline script |
| Page behaviour | vitest page tests | Sort, paging, search, near toggle, CSV order and metadata, disabled items show their reasons |
| Loading states | page smoke with a slow catalog, run and preview | The shared ring shows; the preview chart is emptied while a new ticker loads; the page stays responsive (M253) |
| Visual 1:1 | `tests/visual/compare.mjs` + `diff.py` (Backtest precedent), fixture mode | Layout equals the prototype except the documented changes |
| Accessibility | page tests | `aria-sort`, keyboard-reachable rows, dialog focus return, `aria-live` toast |
| Chips and remarks (P4) | page tests | Both chips on by default with their counts; turning one off lists the hidden tickers with the Remark column, the preview remark and the CSV remark code and date; a cell marked `PRICE_BREAK_IN_LOOKBACK` shows its value with the mark and the ex-date tooltip |
| Page-load sequence (PAGE LOAD SEQUENCE 6c.9) | `verification/screener/page_timing_dev.py` (read-only, after each deploy); page smoke with late data | The targets of 6c.7 (P28): frame first paint, first results and preview; the S2 requests start together; a warm open of the same publication gets `304` for catalog and universe and sends no run when the cached result is current; no request to the bucket; no long task over 50 ms; the late-data cases of 6c.9 item 2 |

### 10b.13 End to end

1. **Local (Phase 0/1, no deploy):** Chromium with a fixture worker and a fixture terminal-api: page → edge-bff → worker → render → preview → CSV → save → Send to Backtest → Backtest import. Pass: every step renders real answer values; no console error.
2. **Dev (under the go of 2026-10-28), recorded in `verification/screener/E2E.md`** with deployment IDs and the publication's `finished_at`:
   - a default-only screen, a custom-parameter screen, an event screen and a preset; for a sample of 20 tickers, each cell is recomputed independently from the published packs with `F` and must equal the answer;
   - the dynamic path against Feature 04 at its stored non-default configurations (`sma_50`, `ema_12`, `ema_26`, `ema_50`, `ema_200`) on the same date, cells reporting `source:"dynamic"`;
   - every event date checked against the bars;
   - preview chart bars equal the Terminal's bars for the same ticker;
   - saved screen survives a reload; CSV opens with the metadata header;
   - Send to Backtest lands in the Backtest page with the same conditions and parameters and the full `definition`, and the Backtest worker's deployment ID is unchanged;
   - a screen reads 0 bytes from terminal-display (refresh log and run log);
   - the two universe chips hide the stale and price-break tickers the catalog counts, and show them with their remarks when turned off (P4);
   - the page timings of PAGE LOAD SEQUENCE 6c.9, recorded in `verification/screener/PAGE_TIMING.md`.


## PERFORMANCE EVIDENCE

This section gives every number measured during the read-only audit of 2026-10-27.
- It is **preliminary evidence for the approval gate, not the Phase 17 benchmark.** Nothing was measured on Railway, under concurrency, or through the real EDGE request path.
- Estimates are labelled INFERENCE and give their inputs.

**Evidence.** Evidence notation as in the header: `audit/<area>.md` and `audit/verify_<area>.json` (reports and verifications), `evidence/<area>/<file>` (raw outputs), all relative to `verification/screener/`; repository `path:line` citations are at `main` `010af1e`.

**Labels.**
- FACT: measured, or read from a recorded log or document.
- INFERENCE: estimated or concluded.
- PROPOSED: a recommendation.
- UNKNOWN: not established.

---

### 11.1 Machine and conditions

| Item | Value | Label and evidence |
|---|---|---|
| Compute host | Audit sandbox with 4 CPUs; node v22.22.0. Every scenario ran in its own process on a single JS thread, 3 repetitions per process. The report gives the first repetition (cold JIT) and the minimum of 3. Wall time from `performance.now`; CPU from `process.cpuUsage` (user + system; GC helper threads can push CPU above wall); peak RSS from `process.resourceUsage().maxRSS`. | FACT: `audit/benchmark.md` section 0 |
| TA-Lib checks | Scratch venv: Python 3.13, TA-Lib 0.6.8, C 0.6.4, numpy 2.3.5. Production uses `python:3.12-slim`. | FACT: `audit/verify_feature04.json` row correction "Section 6 tests" |
| Database path | PostgreSQL 18.6 reached through **pgweb over the internet** (HTTP + JSON), role `pgweb`, read-only, statement timeout 30 s. pgweb adds about 0.2-0.3 s of HTTP round trip on top of execution time. Timings below are server execution times from `EXPLAIN (ANALYZE, BUFFERS)` unless marked. | FACT: `audit/benchmark.md` section 3; `audit/flow.md` header |
| Database settings | `shared_buffers` 128 MB (16,384 × 8 kB); `work_mem` 4 MB; `effective_cache_size` 4 GB; `max_parallel_workers_per_gather` 2; database size 42 GB | FACT: `pg_settings`; `audit/verify_flow.json` confirmed "Section 1 table" |
| Database host | Railway `Postgres` service in `sfo` with a 4 GB memory limit; `max_connections` 500 | FACT: `.railway/railway.ts:9-13` (region, memory); live `current_setting('max_connections')` = 500 (read-only query, 2026-10-28) |
| Cache state | Not controlled. Several auditors queried the same database at the same time. "Run 1" is the first touch in a session, not a guaranteed cold read. A verifier's "warm" re-run still read 26,908 blocks from outside `shared_buffers`, so "warm" means OS-cache best case. | FACT: `audit/benchmark.md` section 3; `audit/verify_flow.json` C12 |
| Not measured | Railway-internal network latency; psycopg from a Railway service; concurrent screens; cache hit ratio; bytes downloaded from terminal-display; terminal-api `/bundle` timings (no HTTP call was made) | FACT |

---

### 11.2 Data pull (full price history)

| Item | Value | Label and evidence |
|---|---|---|
| Query | `ticker, date, open..volume::float8` where `timeframe='Daily' and is_final`, 18 half-year chunks from 2018-01-01 to 2027-01-01, `order by ticker, date` | FACT: `evidence/benchmark/scripts/pull.py` |
| Rows | 1,330,722 rows, 845 tickers (844 stocks + IHSG), 2018-01-02..2026-10-27; every row final and daily | FACT: per-year group-by |
| Pull time (benchmark) | 44.2 s wall in total. Client round trips 0.86-5.9 s per chunk. Server `query_duration_ms` 182-5,261 ms per chunk, 29.1 s in sum (2018-2021 chunks 2-5 s, likely cold; 2021-H2 onward 0.2-1.5 s). | FACT: `evidence/benchmark/data/pull_log.json` |
| Pull time (verifier) | 17.6 s in 29 batches for the same 1.33 M bars | FACT: `audit/verify_matrix_a.json` additional findings |
| pgweb JSON per chunk | 2.75-5.52 MB | FACT |
| Stored full history | `price_full.json` 52,843,773 B (13,474,582 B gzip -9); at most 2,127 bars per ticker | FACT: `audit/benchmark.md` section 1 (the dump itself is local, not committed: market data; rows per chunk in `evidence/benchmark/data/pull_log.json`) |
| Stored 3 years (≥ 2023-10-01) | 576,678 rows, 845 tickers, 21,680,993 B (4,460,902 B gzip); at most 731 bars per ticker | FACT: `audit/benchmark.md` section 1 (dump local, not committed) |
| Rows per recent date | 829-835 tickers per date (2026-10-15..27) | FACT |
| In-memory load | JSON parse plus bar build: 0.43-0.64 s wall, 0.54-0.78 s CPU. After the load: RSS 229 MB, heap 110 MB. Peak RSS of a load-only process: 279 MB. | FACT: `evidence/benchmark/results/load_full.metrics.json`, `evidence/benchmark/results/run_all.log` |
| Caveat | The pgweb pull is an upper bound for this path. It is not representative of a Railway-internal read. | INFERENCE: `audit/benchmark.md` section 4 |

---

### 11.3 Whole-universe compute

#### 11.3.1 Benchmark scenarios (845 tickers, single thread, data in memory)

Times are in ms, shown as first repetition / minimum of 3; CPU is for the first repetition. All formulas were imported read-only from `indicators.ts` and `conditions.ts`. (FACT: `evidence/benchmark/results/{a,b,c,abc}_*.metrics.json`, `evidence/benchmark/results/run_all.log`.)

| Scenario | Full history (1,330,722 bars) | Last 750 (609,500) | Last 500 (414,583) | Last 250 (209,725) | From 2023-10-01 (576,678) |
|---|---|---|---|---|---|
| (a) RSI(7) latest + `rsi < 30` | 123.8 / 80.5 (CPU 172) | 64.2 / 37.0 | 47.9 / 30.8 | 34.8 / 18.2 | 63.1 / 46.7 |
| (b) SMA(75), state `close > sma` | 141.2 / 89.7 (CPU 185) | 85.8 / 56.4 | 51.0 / 30.0 | 31.7 / 17.2 | 87.3 / 47.2 |
| (c) MACD(12,26,9) `crosses_above` signal, last event ≤ 4 bars ago | 250.5 / 161.5 (CPU 338) | 136.1 / 93.3 | 120.6 / 57.7 | 68.6 / 46.6 | 129.3 / 92.0 |
| (a)+(b)+(c) on one `Calc` per ticker | 461.1 / 353.7 (CPU 565); repeat processes 563.5 / 427.7 and 474.8 / 413.6 | 258.0 / 233.7 | 182.0 / 118.0 | 142.3 / 109.2 | 236.3 / 150.7 |

- Peak RSS per scenario was 278-299 MB, mostly the loaded input data (FACT).
- Match counts were identical in every window (FACT): 183 / 166 / 221 / 0 (see TEST EVIDENCE T5).
- The reuse audit measured 5 typical conditions on 40 tickers at 1.15 ms per ticker. That extrapolates to about 0.97 s for 845 tickers (FACT for 40 tickers; the extrapolation is INFERENCE; `evidence/reuse/timing.txt`).

#### 11.3.2 All 53 indicators at registry defaults (76 outputs)

Benchmark, 845 tickers. FACT: `evidence/benchmark/results/all53_*.metrics.json`, `evidence/benchmark/results/repeat*_all53_full.metrics.json`.

| Window | Sum of first-rep wall (ms) | Sum of min wall (ms) | First-rep CPU (ms) | Output values in one pass |
|---|---|---|---|---|
| Full history | 9,074 (repeats 10,192 / 9,553) | 8,079 (repeats 8,950 / 8,796) | 9,639 | 101,134,872 (771.6 MB as float64 if every series were kept) |
| Last 750 | 4,406 | 3,772 | 4,960 | 46,322,000 |
| Last 500 | 3,200 | 2,646 | 3,863 | 31,508,308 |
| Last 250 | 1,799 | 1,363 | 2,372 | 15,939,100 |
| From 2023-10-01 | 4,312 | 3,687 | 4,898 | 43,827,528 |

- Peak RSS: 299 MB.
- Slowest indicators on full history (min ms): CCI 573, Stochastic 328, Donchian 325, Stoch RSI 321, Hist. vol 314, VWAP 305, Williams %R 283, CMF 268, Aroon 264. Fastest: EMA 43, Volume SMA 46, Volume EMA 46, KAMA 49. The top 5 take 23% of the total. Full table: `evidence/benchmark/results/all53_full.metrics.json` `per_indicator`.

**Other measurements of the same work.** They differ because method and sample differ.

| Source | What | Result | Label |
|---|---|---|---|
| matrix_a verifier | All 27 defaults of I01-I27, full history, all 845 tickers, one core | 6.55 s (7.76 ms/ticker) | FACT: `evidence/verify_matrix_a/v_market.txt` |
| matrix_a auditor | Same 27, BBCA only | 6.9 ms/ticker, extrapolated to about 5.8 s | FACT (one ticker) / INFERENCE (extrapolation): `evidence/matrix_a/bench.txt` |
| matrix_b auditor | 26 functions I28-I53 on BBCA's 2,125 bars after warm-up | 5.2 ms (VWAP slowest, 0.53 ms); about 3.27-3.3 s extrapolated to 1,330,722 rows | FACT / INFERENCE: `evidence/matrix_b/bench_report.txt` |
| matrix_b verifier | Same 26 on BBCA | 4.69 ms (VWAP 0.40, CMF 0.37, HV 0.31 ms); about 2.9-2.94 s extrapolated | FACT / INFERENCE: `evidence/verify_matrix_b/bench_report.txt` |
| html_model | All 53 for 844 tickers × 2,125 bars | 11.5 s (13.6 ms/ticker); RSI alone 79 ms | FACT: `audit/html_model.md` 3.4 |
| reuse | All 53 on 40 tickers (63,564 bars) | 17.4 ms/ticker, about 14.7 s extrapolated to 845 | FACT (40 tickers) / INFERENCE (extrapolation): `evidence/reuse/timing.txt`. Superseded by the benchmark's full-universe 8.1-10.2 s. |

INFERENCE (`audit/benchmark.md` 2d): a nightly precompute of all 53 defaults over full history costs about 8-10 s of single-thread CPU, and about 4× less on 4 CPUs.

#### 11.3.3 Long custom lengths (whole market, n = 1000, one core)

FACT, measured on all 845 tickers (`evidence/verify_matrix_a/v_bench.txt`). These figures replace the auditor's BBCA × 845 extrapolations (`evidence/matrix_a/bench_len.txt`: CCI 12.6 s, HMA 3.7 s, Aroon 2.5 s), which were 40-60% too high.

| Indicator (parameter = 1000) | Market time | ms/ticker |
|---|---|---|
| CCI | 7.93 s | 9.39 |
| StochRSI (`stoch_length`) | 2.63 s | 3.11 |
| Williams %R | 2.58 s | 3.05 |
| HMA | 2.19 s | 2.59 |
| Stochastic (`k_length`) | 2.05 s | 2.43 |
| Donchian | 1.26 s | 1.49 |
| Aroon | 1.23 s | 1.46 |
| WMA / KAMA / SMA (O(N) kernels) | 0.09 / 0.06 / 0.05 s | ≤ 0.11 |
| CCI at its default (20), for comparison | 0.56 s | 0.67 |

- FACT: the registry sets no maximum on these lengths. 67 integer parameters have `min: 1` and no max (`audit/reuse.md` C10).
- INFERENCE (verifier): a length cap is advisable, but the cost risk is moderate.

#### 11.3.4 Decoding published price packs

| Measurement | Result | Label and evidence |
|---|---|---|
| All 845 packs, rebuilt with the publisher's encoding, read through `inflateVerified` + `priceSeries` | 2.92-3.32 s wall sequential, 2.77 s with 16 concurrent; CPU 2.9-3.4 s; RSS up to 190 MB | FACT: `evidence/benchmark/results/decode_packs.txt` |
| 40 sampled packs | 5.19 ms per ticker, about 4.4 s extrapolated to 845 | FACT / INFERENCE: `evidence/reuse/timing.txt` |
| Relative cost | Decoding costs about 7× the 3-condition screen | FACT (ratio of measured times): `audit/benchmark.md` section 4 |

---

### 11.4 Tail-window effects

**Cost (FACT, tables above).**
- Cutting to the last 500 bars cuts the 3-condition screen from 354-461 ms to 118-182 ms, and all-53 from 8.1-9.1 s to 2.6-3.2 s.
- Cutting to 250 bars cuts them to 109-142 ms and 1.4-1.8 s.

**Correctness.** Each cut changes values; see TEST EVIDENCE T4.
- K = 500 reproduces the default MACD, RSI, ATR and ADX within 1e-9, except KVO.
- Cumulative series, KAMA in flat regimes, KVO and long custom lengths need full history.
- Calendar windows are unsafe because they are not bar windows. XSPI has 64 bars since 2023-10-01 and DEFI has 240.

**Conclusion.**
- INFERENCE: the compute saving of a tail window is a few hundred ms per screen, or a few seconds for all 53, while full history is the only rule that is exact for every parameter.
- PROPOSED (audit input): evaluate on full history, and bound custom lengths if a window is ever introduced.

---

### 11.5 Payload and file sizes

| Item | Size | Label and evidence |
|---|---|---|
| Screen result: 845 rows of ticker + 5 values (close, rsi7, sma75, macd, signal) | Objects at full precision: 112,458 B JSON / 37,066 B gzip. Objects at 10 significant digits: 91,912 / 27,472. Columnar at 10 significant digits: 49,722 / 23,552. | FACT: `evidence/benchmark/results/abc_full.metrics.json` |
| Latest-value matrix: 76 outputs × 845 tickers (64,220 values) | 737,916 B JSON / 324,382 B gzip at 10 significant digits | FACT: `audit/benchmark.md` 2d |
| Price packs, all 845 tickers, full history | 14.22 MB gzip / 65.0 MB JSON; median 17.2 KB, p90 25.6 KB, max 42.3 KB (BRPT); built in 25.4 s (Python) | FACT for the rebuild; INFERENCE that it equals the published bytes: `evidence/benchmark/results/packsize.json` |
| Price packs, last 750 bars | 6.38 MB gzip; median 7.5 KB, max 16.4 KB (PANI) | FACT: same file |
| Earlier estimate from 30 sampled packs | 12.4 B per row → about 16.5 MB gzip for the market | INFERENCE: `evidence/reuse/pack_size.txt` (superseded by the full rebuild) |
| Cross-sectional recent-window file | K = 260: about 2.0 MB; K = 400: 3.1 MB; K = 520: 4.0 MB gzip | INFERENCE, extrapolated from 30 tickers: `evidence/reuse/pack_size.txt` |
| One preview | Price pack about 17 KB median; IHSG 42 KB | FACT |
| Broker files | The 12 largest stocks together: 28.4 MB gzip and 2,494,454 rows. BBRI archive: 2.2 MB gzip / 14.5 MB inflated. | FACT (documents): `apps/edge-bff/backtest/CONTRACT.md:186-187`; `BACKTEST_END_TO_END.md:421` |
| Flow query results | F06 latest cross-section: 865 rows of 304 B each. Q2b: 124 KB. Q3-20: 106 KB. Q4: 110 KB (890 rows). Q7 one-date grid: 137 KB (890 rows). | FACT: `audit/flow.md` section 5 |
| edge-bff request body cap | 131,072 B; a list of 845 tickers is about 6 KB | FACT: `apps/edge-bff/app/main.py:228-234` |
| Browser cache | IndexedDB `terminal-files`, 50,000,000 B, shared by the Terminal and the Backtest page through one rack module | FACT: `apps/edge-bff/terminal/src/data/rack.ts:15-16` |

---

### 11.6 Default-path query latencies (PostgreSQL)

#### 11.6.1 Feature 04 and Price, benchmark area

Run 1 is the first touch; run 2 follows immediately. FACT: `evidence/benchmark/explain/e1_f04.out`, `evidence/benchmark/explain/e2_price.out`, `evidence/benchmark/explain/e3_window.out`.

| Query | Rows | Run 1 exec | Run 2 exec | Buffers (run 1) | Plan |
|---|---|---|---|---|---|
| F04 latest per ticker, `DISTINCT ON` over the last 30 days | 840 | 1,785 ms | 89 ms | hit 1,018, read 6,366 | Bitmap on `trade_date_idx`; 7,364 heap blocks for 18,235 rows; sort |
| F04 `LATERAL … ORDER BY trade_date DESC LIMIT 1` per universe ticker | 844 | 65 ms | 27 ms | hit 2,528, read 884 | PK backward scan, 845 probes |
| F04 snapshot `trade_date = max(trade_date)` | 828 | 1.7 ms (pages just read by the previous query) | 1.6 ms | hit 846 | Bitmap on `trade_date_idx` |
| Price: latest close, previous close, 1D change, 20-day mean of close × volume (`LATERAL`, last 21 rows) | 845 | 2,288 ms | 31 ms | hit 18,768, read 1,412 | `Price_..._final_idx` (ticker, date DESC) |
| Price: same columns with date-bounded window functions (45 days) | 842 | 117 ms | 84 ms | hit 507, read 131 | Bitmap on `date_idx`, 585 heap blocks |
| Price: 3-year window, whole universe | 576,678 | 16,076 ms (14.1 s in the bitmap index scan with only 1,209 block reads; INFERENCE: I/O contention or a cold volume) | 857 ms | read 13,584; sort spills 37 MB to disk | Bitmap on `date_idx` + external merge sort |
| Price: full history, whole universe | 1,330,722 | 3,015 ms | 1,374 ms | read 33,717 | PK index scan |

#### 11.6.2 Feature 04, Feature 04 area (auditor) and verifier re-runs

| Query | Auditor | Verifier re-run | Evidence |
|---|---|---|---|
| `DISTINCT ON (ticker)` latest row, `trade_date ≥ latest − 10`, 21 columns | 22.0 ms (1,019 hits, 1 read); 5,953 rows → 835 tickers (828 current + 7 stale) | 17.4 ms (835 tickers) | `evidence/feature04/q13_plans.out`; `evidence/verify_feature04/v09_plans.out` |
| `SELECT *` on the latest equity date | 1.97 ms warm | 16.7 ms (843 heap buffers for 828 rows) | same |
| Latest date with `rsi_14 < 30 AND close > sma_50`, joined to price | 84.1 ms cold (837 reads; 839 heap blocks, about one row per page) | — | `evidence/feature04/q23_join_plan.out` |
| `max(trade_date)` | 0.07 ms (index-only backward) | — | `evidence/feature04/q13_plans.out` |
| BBCA, 3 years, `SELECT *` | 17.7 ms (63 reads) | — | `evidence/feature04/q14_plans_wide.out` |
| All equity, 90 days, 4-5 columns | 2,579 ms (17,100 reads) | 824 ms partly warm (19,600 buffers) | `evidence/feature04/q14_plans_wide.out`; `evidence/verify_feature04/v09_plans.out` |
| Per-ticker 1-year max/min close | 2,243 ms (24,321 reads); the same on Price: 1,649 ms | Not re-run; UNKNOWN whether it reproduces | `evidence/feature04/q14_plans_wide.out`; `audit/verify_feature04.json` uncertain F04-08 |
| Full-table GROUP BY | > 30 s (timeout) | An unchunked ≥ 2024 count also timed out | `evidence/feature04/q08_versions.out`; `evidence/verify_feature04/v06_versions2.out` |
| Latest-date F04 + F01 cross-section | 94.6 ms cold (bitmap scans on both date indexes) | — | `audit/verify_matrix_b.json` b-I28-I29-I31-derivable-f04 |

**Physical layout (FACT, with one INFERENCE).**
- The F04 heap is 2,479 MB in 317,373 pages: 4.36 rows per page. The same-schema `_INDEX` table holds 19.88 rows per page. Row widths sum to 359 B. `trade_date` correlation is −0.038 (`evidence/verify_feature04/v02_tables.out`; benchmark pg_stats).
- One date's 828 rows sit on 843 heap pages, about one row per page.
- INFERENCE (verifier): about 1.93 GB of free space inside pages, not dead tuples (`n_dead_tup` 4,775). It affects multi-day windows. The latest-date path is slow only because rows are clustered by ticker; VACUUM FULL or pg_repack would not change that. Only CLUSTER by date or a narrow latest-snapshot table would. `pgstattuple` is not installed, so the figure is not measured directly.

#### 11.6.3 Price full read (reuse area)

| Query | Result | Evidence |
|---|---|---|
| Full price seq scan | 1,330,722 rows, 1,982 ms server-side, 49k buffers | FACT: `audit/reuse.md` 3.4 option E |
| Recent window `date ≥ 2024-08-01` (bitmap) | 429,832 rows, 2,138 ms | FACT: same |

---

### 11.7 Flow query latencies (cold / warm, with re-run variance)

As-of date 2026-10-27. Calendar: d5 = 2026-10-21, d10 = 2026-10-14, d20 = 2026-09-30, d61 = 2026-07-31 (from the F03 date index, 61 rows, 42 ms warm). The recorded single runs are confirmed against the saved EXPLAIN outputs (`audit/verify_flow.json` C12). The re-runs are the verifier's, 19:58-20:03 UTC.

| ID | Query | Plan | Run 1 | Run 2 | Verifier re-runs | Result | Evidence |
|---|---|---|---|---|---|---|---|
| Q1 | F06 latest cross-section, Regular, 16 columns | Bitmap on `(trade_date, market_board)`; 176 heap blocks | 22.6 ms | — | — | 865 rows | `evidence/flow/bench_q1_f06_xsection.txt` |
| Q2 | F06, 61 sessions, calendar through a CTE join without a literal date bound | **Seq Scan of F06** (planner misestimate) | 18,634 ms | — | — | — | `evidence/flow/bench_q2_f06_window_run1.txt` |
| Q2b | Same as Q2 with a literal date range | Skip-scan on the F06 pkey (1,717 index searches; about 22k blocks) | 1,533 ms | 583 ms | 3,259 ms; 7,324 ms; one statement timeout > 30 s with the same plan | 1,525 tickers including warrants and ETFs (844 universe), 124 KB | `evidence/flow/bench_q2b_*`; `evidence/verify_flow/bench_q2b_verify.txt`, `evidence/verify_flow/bench_q2b_verify2.txt`, `evidence/verify_flow/bench_q2b_verify3.txt` |
| Q3-10 | F05 top-3 net, bandar ratio, top-3 VWAP vs close, 10 sessions | Index scan `trade_date_idx`, 243k rows | 4,265 ms | 549 ms | — | 886 tickers | `evidence/flow/bench_q3_f05_10d_*` |
| Q3-20 | Same, 20 sessions | 483k rows; HashAgg spills 30 MB | 852 ms | 545 ms | 4,894 ms (9,866 blocks read) | 890 tickers, 106 KB | `evidence/flow/bench_q3_f05_20d_*`; `evidence/verify_flow/bench_q3_20d_verify.txt` |
| Q3-60 | Same, 60 sessions | Parallel: **2 workers + leader** (corrected from "3 workers"); 1.50 M rows; per process about 30 MB HashAgg spill + about 10 MB external sort | 12,271 ms | 1,918 ms (still read 26,908 blocks) | — | — | `evidence/flow/bench_q3_f05_60d_run1.txt:37-51`, `evidence/flow/bench_q3_f05_60d_run2.txt` |
| Q4 | F03 20-session institutional/retail/foreign net, value, breadth average, latest top-3 share and HHI | Index scan `(date, market_board, ticker)`, 17k rows | 347 ms | 14 ms | — | 890 rows, 110 KB | `evidence/flow/bench_q4_*` |
| Q5 | F05 one broker (YP) × all tickers × 5 sessions | `trade_date_idx`, 117k rows filtered away | — | 31 ms | 31-34 ms | — | `evidence/flow/bench_q5_*` |
| Q5-20 | F05 one broker × all tickers × **20** sessions, Regular | Parallel index scan on `trade_date_idx`, 156,650 rows filtered; F05 has no (broker, trade_date) index | — | — | 85-103 ms | — | `evidence/verify_flow/bench_q5_20d_run1.txt`, `evidence/verify_flow/bench_q5_20d_run2.txt` |
| Q6 | F02 latest date, Regular, per (ticker, broker) | Bitmap `(date, market_board, ticker)`, 24.5k rows | 215 ms | 55 ms | — | **Semantically incomplete**: F02 is sparse on the latest date | `evidence/flow/bench_q6_*` |
| Q7 | One-date snapshot grid from F05 (D 5/10/20 × top 3/5, VWAP 10, breadth, top-3 share 20, top buyer/seller 20) | `trade_date_idx`, about 483k rows | 4,726 ms | 1,466 ms | 4,085 ms (8,958 blocks read again) | 890 rows, 137 KB | `evidence/flow/bench_q7_*`; `evidence/verify_flow/bench_q7_verify.txt` |

**Planning figure (FACT, verifier).** Whole-universe multi-date F06 or F05 aggregates on this 128 MB-buffer database take **about 3-8 s, with occasional timeouts**. The auditor's "warm" figures (0.55-1.9 s) do not reproduce (`audit/verify_flow.json` refuted C12).

**Why (FACT, verifier).**
- F06 is ordered by ticker on disk (pg_stats correlation: ticker 0.969, trade_date 0.047). A multi-date cross-section is therefore scattered random reads (Q2b: about 22k blocks through 1,717 pkey searches).
- The latest date is cheap (Q1: 176 heap blocks). INFERENCE: freshly re-inserted rows sit together.
- Fixed-window metrics read from the latest F06 row stay in milliseconds.

**Planner trap (FACT).** Joining F06 to a CTE calendar without a literal date range picks a 1.25 GB sequential scan (Q2, 18.6 s). Any implementation must pass explicit date bounds.

---

### 11.8 Published-file path estimates (INFERENCE)

**Inputs (FACT, from documents and code; terminal-api was not called).**
- `loadMarket` calls `/bundle` once per ticker in step 1 (load.ts:113-127). A ticker re-bundles only when its answer is no longer usable and it is not cached (load.ts:147).
- Each `/bundle` takes the per-subscriber advisory lock, runs the usage aggregate over the subscriber's last day (`store.py:60-66`; index `(subscriber_id, at DESC)`) and inserts 1 `terminal.access_log` row (terminal-api `main.py:318-332`). `access_log` reltuples: 6,334 (2.36 MB).
- Documented speeds (`BACKTEST_END_TO_END.md` 6.2, 6.5, 7.3, 7.4, 15):
  - `/bundle` median 166 ms from `sfo`, 0.53 s median with 20 concurrent calls;
  - file download 2,268 ms median from `sfo`;
  - 845 `/manifest` calls 2.3 s;
  - 16 download lanes.
- URL TTL 120 s with a 60 s HTTP-timeout margin.
- Per-object bucket latency about 0.8 s over HTTP/1.1; 5 objects in 0.94-1.16 s with 6 connections (ERRORS M240, EXEC-TERMINAL-SPEED).
- Default quotas: 60 files/h, 30 tickers/h, 150 tickers/day, 300 MB/day (migration `20261025_100` l.79-83). The gateway account override (1e9, TEMPORARY) could not be read live.
- `MAX_PORTFOLIO_TICKERS = 12` (engine.ts:151).

**Estimates (INFERENCE, `audit/benchmark.md` section 4).**

| Path | Estimate |
|---|---|
| Cold full-universe load through the worker-style path | 845 `/bundle` calls at about 0.4-0.5 s per 16-lane round ≈ 21-27 s, serialised on one subscriber lock. 845 downloads ≈ 845/16 × 0.5-2.27 s ≈ 26-120 s (small packs may be faster than the 2.27 s median, which was measured on mixed files). Decode about 3 s, compute about 0.4 s. **Total about 50 s to 2.5 min.** Downloads that start more than 60 s after their `/bundle` need a new grant, so the load makes **845 to about 1,690** grant transactions and audit rows, for about 14 MB. |
| Warm load (every pack in the disk cache) | Step 1 still makes 845 `/bundle` calls and 845 audit rows (about 21-27 s), plus about 3 s of decode |
| Browser cold load (Backtest page pattern) | Minutes, from the per-object latency (`audit/reuse.md` 3.4 option B) |
| Default subscriber quotas | Refused (HTTP 429) after 30 tickers per hour. Only the temporarily unlimited gateway account would pass. |
| Database alternative (measured, FACT) | One statement of 1.4-3.0 s server time for full history, or 0.86 s warm for 3 years. Default columns from F04 or Price take 1.6-117 ms warm. Moving the rows into a Railway service was not measured. |

**Existing worker measurements (FACT, worker README and docs).**
- A 12-stock preview downloaded 48 files (28.27 MB). The job after it read them from the disk cache in 4.7 s, against 7.05-7.23 s cold.
- The 12-stock worst case peaked at 1.31 GB of memory.

---

### 11.9 Pipeline and batch timings relevant to precompute

| Item | Value | Label and evidence |
|---|---|---|
| Feature 04 daily equity runs (recent) | 6.2, 7.4, 4.0, 23.2 and 3.1 minutes. The auditor measured runs finishing 2.8-7.4 min after the price run opens (about 10:00-10:04 UTC), with one outlier of 23.2 min. | FACT: `evidence/verify_feature04/v19_fresh.out`; `evidence/feature04/q22_freshness.out` |
| Feature 04 jobs, last 7 days | 4,248 SUCCESS jobs, mean 0.202 s, max 32.9 s; each read exactly 1 source row. Latest equity finish 10:09:36 UTC; bonds 11:03:44 UTC. | FACT: `evidence/verify_feature04/v19_fresh.out` |
| Feature 04 full rewrite (v2) | 844 tickers / 1.318 M rows in 258 s | FACT (document): `RAILWAY_CHANGELOG.md:727` |
| Feature 04 incremental/full shadow | 868 instruments in 311.7 s | FACT (document): `verification/feature04/INCREMENTAL_FINALITY.md` |
| stockbit-updater round `38cdc7dc` (2026-10-27) | APPLY 11:08-12:58 UTC; 48,661 broker rows for 2026-10-26/27; features 2,214.2 s; INDEX 2,077.2 s | FACT: `Monitoring_Stockbit_Update`; `audit/verify_flow.json` C1 |
| Flow snapshot refresh per new date | About 1.5-5 s for the F05 grid plus about 1 s for the F06 part, about 0.3% of the 2,214 s feature refresh | INFERENCE: arithmetic on single-run timings (`audit/flow.md` section 5). The verifier marks the rationale uncertain, and the re-run variance (11.7) suggests the upper end. |
| Flow snapshot size | About 140-400 KB per date; about 35-100 MB a year; a 252-day backfill about 6-20 min one-off | INFERENCE: same basis |
| Precompute of all 53 defaults | About 8-10 s single-thread CPU per run | INFERENCE from 11.3.2 |

---

### 11.10 Caveats

1. **Not the Phase 17 benchmark (FACT).** There were no concurrent screens, no cache-hit-ratio measurement, no terminal-display byte count, no Railway-internal latency and no end-to-end request.
2. **Sandbox, not production (FACT).** Compute ran on a 4-CPU sandbox. Database times came through pgweb over the internet while other auditors queried the same database.
3. **Single-run figures (FACT).** Most database numbers are one or two runs. The flow re-runs were about 3-13× slower than the recorded "warm" runs (Q7 1,466 → 4,085 ms; Q3-20 545 → 4,894 ms; Q2b 583 → 7,324 ms), and one hit the timeout. Feature 04 "warm" timings also varied (2 ms vs 16.7 ms latest-date; 2,579 ms vs 824 ms for 90 days).
4. **Extrapolations (INFERENCE).** Every per-ticker × 845 figure, the pack-size figures from 30 sampled tickers, the cross-sectional file sizes and the published-file latencies are estimates. Where a full-universe measurement exists, it supersedes the extrapolation.
5. **Pack bytes (INFERENCE).** The 14.22 MB total is a rebuild with the publisher's encoding. The published manifests were not read.
6. **Memory (FACT).** The measured peaks (279-299 MB) cover one screen in one process. A long-lived service holding the universe in memory was not measured; it was estimated at about 100-200 MB of RAM (INFERENCE, `audit/reuse.md` 3.4).
7. **Data quality affects meaning, not cost (FACT).** The 2026-09-17/18 price gap, the 16 stale tickers and the PBSA/FORU split breaks change results, not timings (TEST EVIDENCE T7).


## PERFORMANCE BENCHMARK PLAN

Approval item 15: the Phase 17 benchmark. It runs on dev under the go of 2026-10-28 (a Phase 1 step, NEXT ACTION 15.2), on the deployed `screener-worker` with real rack data, and its results replace every provisional limit in API CONTRACT §8.9 (P5). The preliminary single-thread measurements it builds on are in PERFORMANCE EVIDENCE (FACT, `audit/benchmark.md`). Everything here is **PROPOSED** unless labelled.

### 11b.1 Environment

| Item | Setting |
|---|---|
| Services | Dev `screener-worker` (1 replica, `sfo`, memory limit 2 GB to start), dev edge-bff, dev terminal-api and terminal-publisher with the xsection changes |
| Data | The real publication of the day (`price_through`, `finished_at` recorded); 845 tickers, about 1.33 M bars (FACT today: 1,330,722 rows, 2018-01-02..2026-10-27) |
| Threads | `SCREENER_THREADS` K = 1, 2, 4 (separate runs) |
| Timing window | Outside the publisher windows 00:00-01:00 and 12:00-13:05 UTC (ERRORS M250), except the refresh scenarios, which are timed on a real publication |
| Driver | `scripts/screener/bench.mts`, called twice: inside the worker container (worker latency) and from the sandbox through edge-bff (user-visible latency; the sandbox-to-Railway round trip is recorded separately) |
| Database | FACT: `pg_stat_statements` and `pgstattuple` are not installed (only `plpgsql` and `btree_gist`, `audit/verify_feature04.json` F04-10). DB cost is therefore measured with `EXPLAIN (ANALYZE, BUFFERS)` of each new publisher statement and `pg_stat_io` / `pg_stat_database` deltas around a publisher run |

### 11b.2 Method

- Each scenario: 3 warm-up runs, then at least 30 measured runs; report p50, p95, max.
- **Cold** means the first run after a snapshot swap or a restart (tail LRU and result cache empty); **warm** means the same definition again (result-cache hit) or another definition on the same data (tail cache warm).
- Timings come from the worker's structured `run` and `refresh` log lines (TARGET ARCHITECTURE §6.16), so every number can be traced to a log line; the client records end-to-end time.
- CPU per run from `process.cpuUsage` deltas in the log line; peak RSS from `process.memoryUsage` plus Railway's memory metric.
- Bytes and files per refresh from the `refresh` log line; grants and audit rows per refresh from terminal-api's own log (pgweb cannot read schema `terminal`, FACT `audit/benchmark.md` §4).
- Every result is written to `verification/screener/BENCHMARK.md` with deployment IDs, data version and the raw log excerpt location.

### 11b.3 Scenario × metric matrix

Metrics: **L** latency p50/p95 at the worker and through edge-bff; **C** CPU ms; **M** peak RSS; **B** bytes and files from terminal-display; **H** cache hit ratio; **P** payload raw and gzip; **D** DB time and buffers; **X** Backtest job duration delta. In column B, **0** means asserted zero: the scenario is served from the snapshot, and any byte read from terminal-display during it fails the run (from the refresh and run log lines).

| # | Scenario | L | C | M | B | H | P | D | X |
|---|---|---|---|---|---|---|---|---|---|
| S1 | Default-only, 1 / 5 / 10 conditions (snapshot lookups) | ✓ | ✓ | | 0 | ✓ | ✓ | | |
| S2 | One custom indicator: RSI(7) < 30 | ✓ | ✓ | | 0 | ✓ | ✓ | | |
| S3 | Five custom indicators, O(N) kernels (EMA, RSI, ATR, SMA, MACD at non-default lengths) | ✓ | ✓ | ✓ | 0 | ✓ | | | |
| S4 | Five custom indicators, O(N·n) kernels (CCI, Stochastic, Donchian, Aroon, Williams %R) at the derived caps | ✓ | ✓ | ✓ | 0 | | | | |
| S5 | Mixed default + custom + cross-sectional (`rs_rank`), ALL | ✓ | ✓ | | 0 | ✓ | | | |
| S6 | Same as S5 with ANY (no pruning) and with `exhaustive:true` | ✓ | ✓ | | 0 | | | | |
| S7 | Event: MACD crosses above signal within 5 | ✓ | ✓ | | 0 | | | | |
| S8 | Flow (Phase 2): F1 foreign net 20, B1 top-5 net 10, B4 one broker 5 (the flow files' own bytes are measured in S14) | ✓ | ✓ | ✓ | 0 | | ✓ | ✓ | |
| S9 | Whole universe, no condition (`universe_only`) | ✓ | | | 0 | | ✓ | | |
| S10 | Worst case allowed by the provisional limits (20 conditions at caps, ANY, within 130) | ✓ | ✓ | ✓ | 0 | | ✓ | | |
| S11 | The 8 Phase 1 technical presets and their counts | ✓ | ✓ | | 0 | ✓ | | | |
| S12 | Warm vs cold tail cache (same definitions after a swap) | ✓ | ✓ | | 0 | ✓ | | | |
| S13 | Result-cache hit | ✓ | | | 0 | ✓ | | | |
| S14 | Refresh: cold (empty disk cache) vs disk-cached restart (which must grant and download nothing); phases grant, download (sin → sfo), decode, cross-check, defaults, swap; the price and, in Phase 2, flow files | ✓ | ✓ | ✓ | ✓ | ✓ | | | |
| S15 | Publisher run with xsection writing vs the previous run (run time delta, upload bytes) | ✓ | | | ✓ | | | ✓ | |
| S16 | Preview: one ticker, 3 conditions | ✓ | ✓ | | 0 | | ✓ | | |
| S17 | Catalog and universe through edge-bff | ✓ | | | 0 | ✓ | ✓ | | |
| S18 | Concurrency 1 / 2 / 4 / 8 mixed screens (S5 mix), outside a refresh | ✓ | ✓ | ✓ | 0 | ✓ | | | |
| S19 | S18 during a refresh (old snapshot serving, new one building); the screens read 0 bytes, the refresh's own bytes are S14's | ✓ | ✓ | ✓ | 0 | | | | |
| S20 | S18 during a Backtest job (12-stock portfolio) | ✓ | ✓ | | 0 | | | | ✓ |

Baselines to compare against (FACT, single thread, data in memory, wall time, `audit/benchmark.md` §2): RSI(7) 80-124 ms; SMA(75) state 90-141 ms; MACD cross 162-251 ms; the three together 354-564 ms; all 53 defaults 8.1-10.2 s (first-repetition CPU 9.6-10.7 s); decode of all packs 2.8-3.3 s; peak RSS 279-299 MB; CCI(1000) whole market 7.93 s (`audit/verify_matrix_a.json`).

### 11b.4 How limits and concurrency are chosen

Each limit is computed by a rule from the measurements, not chosen by hand; the rule and the inputs go into `verification/screener/BENCHMARK.md`.

| Setting | Rule (PROPOSED) |
|---|---|
| `SCREENER_THREADS` (K) | Largest K for which, at concurrency K, the S5 p95 stays ≤ 1.5 × its single-run p95, peak RSS × 1.5 fits the memory limit, and the S20 Backtest job duration grows ≤ 5% |
| Memory limit | Peak RSS during S19 (old and new snapshot both alive) × 1.5 |
| `SCREENER_QUEUE` | 2 × K, unless S18 at concurrency 8 shows queueing time above the deadline, then K |
| `SCREENER_DEADLINE_MS` | 2 × the S10 p99 wall time at K, at most 20 s |
| `SCREENER_MAX_CPU_MS` (compute budget) | The S10 CPU p99, so every definition inside the published limits passes; definitions costed above it are refused before compute |
| `SCREENER_CAP_BUDGET_MS` and per-parameter caps | The budget that keeps S4 at the caps within the deadline at K; caps then derived per indicator from `cost_class` and the ns per bar measured on the service in this run (with its CPU model and Node version), written into the generated registry; never from the sandbox, never re-measured at start-up (TARGET ARCHITECTURE §6.8) |
| `SCREENER_MAX_CONDITIONS`, `SCREENER_MAX_METRIC_FILTERS`, `SCREENER_WITHIN_MAX` | Kept at 20 / 8 / 130 if S10 fits the deadline; otherwise lowered until it does |
| `SCREENER_MAX_COUNTS` | At least `SCREEN_LIMIT`, as long as a counts request of that size fits the deadline at K; else `SCREEN_LIMIT` is lowered |
| `SCREENER_CACHE_BYTES` | The knee of the S12 hit ratio vs memory curve, within the memory limit |
| `SCREENER_MAX_RESPONSE_BYTES` | 2 × the S9 payload (largest legitimate answer) |
| `SCREENER_MAX_FILE_BYTES`, `SCREENER_MAX_INFLATED_BYTES`, `SCREENER_MAX_REFRESH_BYTES` | 2 × the largest file, inflated document and refresh total measured in S14 (U4, U10) |
| Refresh schedule assumptions | S14 end-to-end time must finish well before the next publication; if download from `sin` dominates, the disk cache (`SCREENER_CACHE_DIR`) is kept on a volume (decision then) |

### 11b.5 Targets to judge the result (PROPOSED; the user may change them)

| Path | Target |
|---|---|
| S1 default-only screen through edge-bff | p95 ≤ 0.5 s |
| S5 mixed screen through edge-bff, warm | p95 ≤ 2 s |
| S16 preview through edge-bff | p95 ≤ 1 s |
| S14 refresh end to end | ≤ 2 min after `finished_at` |
| S20 Backtest job duration | unchanged within 5% |

A target missed is reported with its cause from the log lines and a proposal; no limit is loosened silently.

The page-load targets (frame first paint, first results, preview from the browser) and their timing script are in PAGE LOAD SEQUENCE 6c.7 and 6c.9 (P28); the multi-user scenarios S21-S25 (several owners, two replicas at a publication, fairness, a replica's cold start, the edge-bff relay), the scaling triggers and the cost model are in MULTI-USER SCALE AND COST 6d.9-6d.11. Both run with this benchmark on the same deployments, and S21-S25 extend the matrix of 11b.3.


## RISKS / TRADE-OFFS

Labels and evidence notation as in TARGET ARCHITECTURE. Mitigations are **PROPOSED**.

### 12.1 Risks

| # | Risk | Evidence | Impact | Mitigation | Residual |
|---|---|---|---|---|---|
| R1 | Unadjusted price breaks give false technical signals everywhere ("oversold", "far below MA50", a negative lower band) | FACT: ERRORS D22; `audit/verify_feature04.json` row correction F04-23; live L6: 8 tickers with a price-affecting action between `ADJUSTED_HISTORY_BOUNDARY` and 2026-10-27 (PBSA split; FORU, ENRG and others rights), 5 more dated later | Wrong matches for affected tickers in the Screener, Terminal, Backtest and Feature 04 alike | TEMPORARY, derived rule (TARGET ARCHITECTURE §6.12; P4 and P4.1 A, DECIDED 2026-10-28): a ticker with such an action is hidden by default by the chip "No unadjusted price break"; shown, it carries the row remark `PRICE_BREAK`, and its price-derived cells keep their values, each cell whose lookback contains the ex-date marked `PRICE_BREAK_IN_LOOKBACK`; the run answer warns `PRICE_BREAKS_IN_RESULT` | A shown ticker can still pass "oversold" or "far below MA50" on a distorted value, with the remarks as the only warning (the user's choice, P4.1 A). Not covered: actions missing from `idx_event_annotation`, unadjusted actions before the boundary (D22's earlier adjustment is suspected, not verified), and every other consumer. The data-layer fix (re-pull or rescale history on the corporate action, D22; E2) is a separate approval |
| R2 | Freshness: the Screener is about 3 h behind the database each trading evening by design | FACT: price cron 10:00 UTC; 19:00 WIB publication ends about 13:03 UTC (ERRORS M250) | Users may see the database's newer session elsewhere (AI answers) and not in the Screener | Every response shows `price_through` and `published_at`; one data version for Screener, Terminal and Backtest | Fresher data for all three pages needs a rack schedule change (P1) |
| R3 | Deploy overwrites: CLI deploys of publisher and terminal-api; `/state` (already live, terminal-api `689dc465`) is extended, not created; the Backtest `boot()` was rewritten by EXEC-BACKTEST-LOAD, which has landed on main `010af1e` (`app.ts:37-85`), and Phase 1b builds on it | FACT: ERRORS M248 (its class names terminal-api, the publisher and workers: the last upload wins, in both directions), M252, M253; EXEC-BACKTEST-LOAD and EXEC-BACKTEST-SPIN, done 2026-10-27 (`EXEC.md:8444-8473`) | A branch upload without the latest main removes `/state`, which the backtest worker reads; a merge commit is skipped; the import breaks on a late catalog | The M248 procedure on every CLI deploy (merge the latest main, fetch main before the upload and after SUCCESS, upload the repository layout, compare the live build with the merged tree), or merge to main first and CLI-deploy the merge commit (TARGET ARCHITECTURE §6.17); an additive change to `/state` with its existing tests kept; Phase 1b tested with a late catalog; check the deployment of each merge commit; deploy outside the M250 windows | Another session can still deploy in between; the procedure detects it, it does not prevent it |
| R4 | Flow lag recurs without a new Stockbit token; a partial 19:00 run delays flow by one publication | FACT: one round per stockbit-updater deployment, token expires 2026-10-28 10:53 UTC (`audit/verify_flow.json` refuted C2); INFERENCE: round 11:08-12:58 vs run 12:05 UTC | Flow cells lag price | `flow_through` per cell; `FLOW_LAGGED` beyond the user maximum (P10); completeness gate excludes partial dates | The lag itself is an operations issue outside this design |
| R5 | Memory, threads and `sin` → `sfo` download time are not measured on the service; the shared-memory path depends on the bit-parity gate | UNKNOWN until Phase 17 | Out-of-memory during a refresh (two snapshots alive) or slow refresh | Start at 2 GB; Phase 17 sets the limit at measured peak × 1.5; typed views only after the bit-parity test; disk cache for restarts | — |
| R6 | Long O(N·n) lengths and ANY logic (no pruning) can make one request expensive | FACT: CCI(1000) 7.93 s for the whole market; ANY cannot be pruned (proof, TARGET ARCHITECTURE §6.10) | Slow screens, blocked threads | Derived caps; cost model refuses above the budget before computing; deadline; cancel flag between tickers | Caps are provisional until Phase 17 |
| R7 | No CI: tripwires and parity tests protect nothing unless run | FACT: only `database-schema-docs.yml` runs (`audit/edge_conventions.md` §1.9) | A change to shared code could break the Backtest unnoticed (guarantee I3) | **TEMPORARY:** run the TEST PLAN families by hand before each merge and record each run's output in `E2E.md` or `BENCHMARK.md`; the worker's start-up registry check still stops a mismatched deploy. General fix at the layer that owns the mechanism, repository automation, proposed for approval: a GitHub Actions workflow on PRs touching the screener-worker watch paths that runs `check_backtest_untouched.mjs`, backtest-worker `npm test` and `npm run registry:check`, the Terminal calc tests and the screener core tests (CHANGES AWAITING APPROVAL A9) | Human discipline until A9 |
| R8 | The shipped Screener looks smaller than the prototype: 11 of 26 presets need fundamentals; 6 bandarmology presets wait for Phase 2/3; Ichimoku waits for a registry release; market cap, index, board, notation and free float are disabled | FACT: no fundamental, market-cap, index, board or notation data (`audit/fundamentals_universe.md` §1) | The user may read it as a regression | Everything stays visible with its reason; phase table in CHANGES AWAITING APPROVAL | Data sources are separate decisions (P11) |
| R9 | The planned 2026-09-17/18 price refill would put about 840 tickers into `REPAIR_REQUIRED`, weakening Feature 04 as an oracle until repaired | FACT: `audit/verify_feature04.json` additional findings | Parity tests against Feature 04 fail for affected tickers | Pin the parity record to a date before any refill; the hazard is recorded as ERRORS D26 (2026-10-28) | The Screener runtime is unaffected (Feature 04 is not on its path) |
| R10 | Version skew between page and worker deploys | INFERENCE | Wire-schema mismatch | `schema_version` on every request and answer; the page holds no formula code, so numbers cannot drift | Merge commits skipped by Railway (M252) remain possible |
| R11 | The xsection files on the public terminal-api could be pulled by a direct subscriber | FACT: terminal-api is also public (`terminal-api-dev.up.railway.app`, `audit/edge_conventions.md` §6); `/state` answers subscribers today (`main.py:297-298`, `Depends(subscriber)`) | A 14 MB file per call against that subscriber's quota | `POST /xsection` accepts only proxy-key callers (`main.py:149-154` mechanism); `/state` shows the index but grants no file (the bucket is private); neither route is in the browser allow-list | Object keys and hashes are visible to a direct subscriber; they grant nothing |
| R12 | The refresh cross-check cannot compare pack sha256 values: `/manifest` has no pack entries, and `/state` names only the publication | FACT (main `010af1e`): `/manifest` returns yearly files with `bytes, rows, first, last, sha256` and no `packs` (`apps/terminal-api/app/main.py:307-314`; packs are read only by `/bundle`, `main.py:372`); `/state` returns the `STATE_FIELDS` of `state.json` (`main.py:297-305`, `bucket.py:8, 45-53`) | A publisher bug that writes a slice different from the pack would not be caught by a sha comparison | Publisher unit test (slice = pack); runtime check of last bar and row count per ticker against `/manifest`; optional additive `packs` field on `/manifest` | Content equality between slice and pack is guaranteed by the publisher test, not at runtime |
| R13 | Shared gateway quota: worker, browser and backtest worker draw on one terminal-api subscriber | FACT: `audit/reuse.md` §3.2 | Under default quotas, heavy browser use plus restarts could exhaust `megabytes_per_day` 300 | INFERENCE: the screener needs about 15-30 MB per publication; disk cache avoids repeats; does not depend on the TEMPORARY 1e9 override | Measured in S14/S15 |
| R14 | Floating ties on flat windows decide states such as "OBV above its SMA" | FACT: BNBR 358 of 358 disagreements on flat-OBV windows (`audit/verify_matrix_b.json`) | Borderline cells flip between equivalent histories | Same raw-double rule as the Backtest; liquidity and traded filters; cumulative levels never offered as raw thresholds | A global tie rule is a later core release |
| R15 | Node module resolution: the Terminal's sources use extensionless imports that plain Node cannot load | FACT: ERRORS M249 | The worker fails to start after a Terminal change | Use the backtest worker's loader (`loader/register.mjs`, `resolve.mjs`) and copy it into the image; watch pattern on `/apps/backtest-worker/loader/**` | — |
| R16 | Board default differs from the Terminal (closed by P8 b) | FACT: the user kept all boards as the Terminal Flow default and uses Regular to compare with Stockbit (ERRORS M244); on 2026-10-28 the user chose all boards for the Screener too (P8, DECIDED) | Only the labelled Regular variant now differs from the Terminal flow panel by board; a Nego-only day can still differ by calendar (the Terminal and the Backtest run on price bars; P20 b) | Every flow reference carries `board`, labelled in the cell and the handoff; all-board values recomputed from summed one-day components (TARGET ARCHITECTURE §6.11) | The Regular variant differs from the default and from price volume across boards; it is labelled |
| R17 | The Screener does not store default values, against the brief's expectation | FACT: brief "Do not rebuild all historical indicators every day" | 8.1-10.2 s wall on one thread per publication (first-repetition CPU 9.6-10.7 s), nothing persisted | Acknowledged: P2 (a), DECIDED 2026-10-28 ("P2 OK") | — |

### 12.2 Trade-offs taken

| Chosen | Alternative | What the choice gives | What it costs |
|---|---|---|---|
| One rack data version (P1 a) | An earlier screen build or a DB login | Screener, Terminal and Backtest never disagree on the latest session; no credential in the worker | About 3 h later each evening than the database |
| Recompute defaults in memory per publication (P2 a) | Store defaults in Feature 04 or a new table | One formula path; exact for recursive and cumulative indicators; no migration, backfill or checkpoint | 8.1-10.2 s wall on one thread per publication (first-repetition CPU 9.6-10.7 s); nothing queryable in SQL |
| New `screener-worker` service | Reuse the backtest worker | The Backtest's hashes, limits and threads stay untouched | One more Railway service to operate |
| Server-computed preview | Browser `/bundle` + recompute | No formula code in the page; no grant per click; no drift check | A worker call per preview |
| Rows, gzip | Columnar | Simple UI port and CSV | About 4 KB more gzip per 845 × 5 values at equal precision (`audit/benchmark.md` §2c) |
| Fixed `rs_rank` population (P7 a) | The filtered universe | Ranks stable under filter edits; precomputable; planner-safe | Differs from a user who expects "rank within my filter" |
| Strict Send to Backtest window (P13) | Approximate with W = max N | No silent semantic change | More conditions listed as left out |
| All-board default for flow (P8 b, decided) | Regular (price volume, Stockbit's Foreign Flow) | The same board as the Terminal Flow panel (whose flow, like the Backtest's, runs on price bars; the Screener's calendar is P20 b); `fnet`, `broker`, `top5` transfer to the Backtest with the same formula (values differ only on Nego-only days, which the Backtest's price-bar calendar skips, TARGET ARCHITECTURE §6.11) | Differs from price volume and from Stockbit's Foreign Flow (168 of 841 20-day nets, 20 sign flips); non-additive fields recomputed from summed components; the Regular variant stays as a labelled choice |
| Defer Screen Performance History (P14 a) | A labelled non-point-in-time evaluator | No survivorship or look-ahead in a curve users would trust | The Portfolio123-style view is absent for now |
| Disabled-with-reason items | Hide or approximate them | Nothing fabricated; nothing removed silently | A visibly smaller catalogue (R8) |
| Hide stale and price-break tickers by default, show them with remarks and their values (P4, P4.1 A, decided) | Per-cell NA on a price break (P4 d, recommended); values blanked when shown (P4.1 B, recommended) | The default results hold no distorted ticker; nothing is removed silently; a shown ticker is complete and explained | A shown price-break ticker can match on distorted values, marked only by its remarks, until the D22 fix (E2) |
| `/state` carries the xsection index | Index only in `POST /xsection` | A restart with a warm disk cache grants nothing; only missing files count against `megabytes_per_day` | A direct subscriber can read object keys and hashes (R11) |
| Near rows always computed | Prune by the near toggle | The toggle needs no re-run | Slightly less pruning (cheap: 0.35-0.56 s exhaustive) |

The time until the page shows after the browser opens, and serving many users at low cost (the user's requirements of 2026-10-28), carry their own risks and trade-offs in PAGE LOAD SEQUENCE and MULTI-USER SCALE AND COST.


## UNKNOWNS / PRODUCT DECISIONS

Approval item 16. Labels and evidence notation as in TARGET ARCHITECTURE.

### 13.1 Unknowns and the check that settles each

| # | UNKNOWN | Why it matters | Check that settles it | When |
|---|---|---|---|---|
| U1 | Worker memory, thread count K and refresh time, including the download from the bucket in `sin` to the worker in `sfo` | Memory limit, K, queue depth, refresh delay | Phase 17 scenarios S14, S18, S19 (PERFORMANCE BENCHMARK PLAN) | Phase 1, dev |
| U2 | Whether `F` on SharedArrayBuffer-backed typed views is bit-identical to plain arrays | Decides shared memory vs one copy per thread | `apps/screener-worker/tests/typed_views.test.ts` (53 indicators × 50 tickers) | Phase 0 |
| U3 | Live quota usage of the shared gateway subscriber (pgweb has no permission on schema `terminal`, FACT `audit/benchmark.md` §4) | Whether default quotas would hold without the TEMPORARY 1e9 override | Read `terminal.quota`, `quota_override` and a day of `access_log` with the terminal login or the admin route, after approval; or terminal-api logs | Before Phase 1 deploy |
| U4 | Whether the published price packs equal the audit's rebuild (14.22 MB gzip for 845 tickers) | Upload and download size per publication | Sum of `bytes` in the first `/xsection` answer and in `/bundle` answers for a sample | First dev publication |
| U5 | Whether IDX's own public "foreign net" uses the Regular board or all boards (Stockbit's "Foreign Flow" equals Regular, FACT ERRORS M244 on BMRI for 16 dates) | The label of the Regular variant only: P8 is decided (all boards by default, 2026-10-28) | Compare a sample with IDX published statistics (an external source; not checked, no external call allowed in the audit) | Before Phase 2 |
| U6 | Publisher run time and DB buffers added by the Phase 2 per-date F06 and F05 reads (INFERENCE: about 10-40 s) | Publisher window, shared buffer pool | A bounded read-only `EXPLAIN (ANALYZE, BUFFERS)` of the exact per-date statements with literal bounds through pgweb, now (NEXT ACTION 15.1); then `pg_stat_io` deltas at the first dev run (S15) as confirmation | Before the Phase 2 go |
| U7 | Where the expectation of "about three years" of Feature 04 history came from | Only the user's expectation; FACT: equity history is about 8.8 years (2018-01-02 → 2026-10-27, `audit/feature04.md` §8). No source in code or docs (`audit/verify_feature04.json` F04-24) | Ask the user. No design impact: the Screener uses all published history | Any time |
| U8 | Whether dividend amounts are right for a yield screen (special dividends included; some values look high, for example BBCA 2026-06-17 and 2026-08-31) | Phase 2 dividend metrics | Validate a sample of tickers against an independent source; settle the split-adjustment rule | Before Phase 2 dividends |
| U9 | Whether "retaining existing screener" in the user's follow-up means the prototype's flow presets or the Backtest's `fnet`, `broker`, `top5` conditions (`audit/verify_flow.json` uncertain) | Phase 2 scope wording | Ask the user. The design keeps both: the prototype's flow metrics are mapped (TARGET ARCHITECTURE §6.11), and the Backtest's three are lossless in Send to Backtest | Before Phase 2 |
| U10 | Whether the inflated `price` document (INFERENCE: about 75-80 MB of JSON) decodes within the refresh time and memory budget | Refresh time, worker memory | S14 | Phase 1 |
| U11 | A fundamental data source and its licence (for example the TradingView scanner fields; never checked, `audit/fundamentals_universe.md` §2 row 9) | Everything fundamental | Product decision (P11) and an onboarding per `NEW_TABLE_ONBOARDING_PLAN.md` | Phase 4 |
| U12 | Whether `F` matches TradingView: the workbook names a Pine `ta.*` function on 28 of the 53 rows, but no TradingView output was compared (no external call in the audit; INDICATOR MATRIX §3) | Users may compare Screener values with TradingView charts. The approved formula contract is Feature 04 first, then the Terminal reference engine (user decision 2026-10-25, `EXEC.md:7876-7878`), not TradingView; by code, ATR and ADX follow TA-Lib with no true range on bar 0 | Export TradingView values for 3 tickers and the Pine-referenced indicators and compare them with `F`; differences are reported, not adopted, unless the user changes the 2026-10-25 decision. No design impact | Any time; before the Phase 1 dev E2E if the user wants it in `E2E.md` |

### 13.2 Product decisions

Each decision lists the question, the options, the recommendation and its impact. The recommendations were **PROPOSED**. Where the user has decided, the decision is given with the user's words and the options stay as the record. The user's answers of 2026-10-28 are recorded in `EXEC.md`, section EXEC-SCREENER (the SCREENER item moved there from `PLAN.md` with the go, commit `88d3344`).

**Status on 2026-10-28 (FACT, `EXEC.md` EXEC-SCREENER).**

| Status | Decisions |
|---|---|
| **DECIDED** by the user on 2026-10-28 | P1 (a), P2 (a), P3 (a), P12 (a), as recommended ("P1 OK P2 OK p3 OK ... P12 OK"); P8 (b), all boards, against the recommendation (a) ("--> semua papan"); P4, the user's own choice ("P4 tidak, dihide tapi di remark saat di show di filter table"), which replaces recommendation (d), and its sub-question P4.1: A, values shown with the remark ("P4 - pakai A"), against the recommendation (i) |
| **DECIDED with the go**, as recommended | P5, P6, P7, P15, P16, P17, P18, P19, P21, P22, P23: "Keputusan lain (P5-P7, P15-P19, P21-P23) mengikuti rekomendasi laporan" (EXEC-SCREENER) |
| **Go** | Given on 2026-10-28: "Arti gas maksudnya tetap jalankan sesuai fase, take into account jawaban saya diatas (P1-P4 dan P12)". Execution runs phase by phase on dev (EXEC-SCREENER, "Fase" and "Langkah Phase 1") |
| **Open, raised after the go** | P24-P34 (13.3), from PAGE LOAD SEQUENCE and MULTI-USER SCALE AND COST: Phase 1 builds to the recommendations of P24, P27, P28, P32, P33 and P34, named to the user as EXEC-SCREENER did for P5-P7 (PROPOSED); P29 asks the user for expected usage; P25, P26, P30 and P31 are EDGE-wide items outside the Screener phase |
| **Open, before Phase 1b** | P13 (its recommendation stands until the user confirms it) |
| **Open, before Phase 2** | P9, P10 and P20, decided after the flow indicator proposals the user asked for (FLOW INDICATOR PROPOSALS (PHASE 2), whose 16.11 lists the choices with them); migration 2 and its read source (Feature 06 as designed, or Feature 03 as 16.10 recommends) |
| **Open, confirming what stays disabled** | P11, P14 (fundamentals, market cap and the screen performance history wait for data or their own decisions, EXEC-SCREENER); Phase 1 ships them disabled with reasons (P11 a) and as "Stock vs IHSG" (P14 a) |
| **Not decisions** | U7, U9 and U12 (13.1) |

The new requirements of the same answers are design inputs, not product decisions: multi-user scale at low cost (MULTI-USER SCALE AND COST); the time until the page shows after the browser opens, following the Terminal and Backtest load sequence (PAGE LOAD SEQUENCE); an onboarding document on how the Screener works and how to add indicators or data, written separately. The fourth, at most two agents per workflow, was withdrawn by the user with the go ("Tidak usah pakai batasan maks 2 agents/ workflow ya", EXEC-SCREENER "Batas agen").

#### P1. Market-data source and freshness

- **Question.** Which market-data source does the Screener use, and how fresh must it be?
- **Options.**
  - (a) Rack cross-sectional files written in the existing 07:30 / 19:00 WIB publisher run: one data version with the Terminal and Backtest; the Screener shows the same session they do.
  - (b) Per-ticker rack packs through `/bundle`: no publisher change, but about 845-1,690 grants per publication, and it depends on the TEMPORARY gateway quota override.
  - (c) A separate earlier screen build (about 10:20 UTC): about 3 h fresher each evening, but a second data version across EDGE pages.
  - (d) A direct read-only DB login in the worker: fresher, but a DB credential, a full re-read per version and per restart, and a second data version.
  - Separately: move or add a rack publication right after the price cron, so all three pages get fresher together.
- **Recommendation.** (a). If fresher evening data matters, approve a rack-wide schedule change as its own item rather than a screener-only build. (b) only as a TEMPORARY fallback if the publisher change cannot be approved.
- **Decision (DECIDED, user 2026-10-28).** (a), as recommended ("P1 OK"; `EXEC.md` EXEC-SCREENER). The rack-wide schedule change stays a separate proposal (E1, `FUTURE_PLAN.md`).
- **Impact.** Phase 1 changes terminal-publisher and terminal-api (CLI deploys under the M248 procedure); the worker holds no DB credential; Screener, Terminal and Backtest show the same latest session, about 3 h behind the database each trading evening. FACT (main `010af1e`): `GET /state` already exists (EXEC-BACKTEST-LOAD K1, `apps/terminal-api/app/main.py:297-305`); the proposal adds one field to it, the `xsection` index (`STATE_FIELDS`, `apps/terminal-api/app/bucket.py:8`), and one new route, `POST /xsection`, for proxy-key callers only. FACT: the edge-bff gateway does not forward `/state`: its allow-list `TERMINAL_ROUTES` (`apps/edge-bff/app/main.py:34-36`) holds `manifest`, `reference`, `history`, `logo`, `files` and `bundle` only, and the only caller of `/state` is the backtest worker (`apps/backtest-worker/src/terminal.ts:595-603`). The design does not need the gateway to forward it: the screener-worker calls terminal-api over the private network with the proxy key, and the page learns the publication from `/api/v1/screener/catalog` (its `data` block, API CONTRACT §8.3). Keeping `/state` and `/xsection` out of the browser allow-list is part of the hard constraint against full-market data in the browser (CHANGES AWAITING APPROVAL 14.7).

#### P2. Feature 04's role and the per-publication recompute

- **Question.** What role does Feature 04 play, and is the in-memory recompute of defaults per publication acceptable?
- **Options.**
  - (a) Feature 04 unchanged and never read at runtime: a parity oracle in tests, with optional per-publication reconciliation. The 53 defaults (76 outputs) are recomputed by `F` in memory per publication: 8.1-10.2 s on one thread over full history (wall; first-repetition CPU 9.6-10.7 s), nothing stored, not incremental. This is the brief's Option C (mixed model) without a runtime Feature 04 read (DATABASE / FEATURE CHANGES §7.3).
  - (b) Read Feature 04 at runtime for the 9 indicators it fully covers: needs a grant, adds a second time base, couples to `REPAIR_REQUIRED`.
  - (c) Extend Feature 04 (Option A): double implementation, a VERSION bump that invalidates 6,076 checkpoints, a 1.39 M-row rewrite.
- **Recommendation.** (a). It departs from the brief's expectation that defaults come from stored precomputed data and from "do not rebuild all historical indicators every day": the Screener writes nothing, and exactness for recursive and cumulative indicators needs full history or checkpoint state.
- **Decision (DECIDED, user 2026-10-28).** (a), as recommended ("P2 OK"), including the departure from the brief named above.
- **Impact.** No Feature 04 migration, backfill or worker change; the publisher group needs SELECT on F04 only for the optional reconciliation file (Phase 2, C5).

#### P3. The new runtime service and how it deploys

- **Question.** Approve the `screener-worker` service, and choose its deploy source.
- **Options.** Service: a new private `screener-worker` (Node 22, no dependencies, `sfo`, no DB or bucket credentials). Deploy: (a) GitHub `main` with watch patterns on the shared core (feature-04-worker precedent); (b) CLI upload like backtest-worker.
- **Recommendation.** Approve the service, deployed by (a), to dev only and outside the publisher windows.
- **Decision (DECIDED, user 2026-10-28).** The service, deployed by (a), as recommended ("p3 OK"). It is created in Phase 1, on dev, through the pinned IaC plan (TARGET ARCHITECTURE §6.17). How it scales for many users is designed in MULTI-USER SCALE AND COST.
- **Impact.** One Railway service, its variables and an edge-bff URL/key pair; `.railway/railway.ts` and `RAILWAY_CHANGELOG.md` updates. With (a), a change to `indicators.ts` or the core redeploys the Screener automatically.

#### P4. Stale tickers and unadjusted price breaks in the default universe

- **Question.** What does the default universe do with stale tickers and with tickers whose stored prices break across a corporate action?
- **Options.**
  - Stale (16 today): (a) excluded by a visible default chip "Traded on evaluation date", flagged when included; (b) included and flagged.
  - Price breaks, by a derived rule (TARGET ARCHITECTURE §6.12): a price-affecting action with `ADJUSTED_HISTORY_BOUNDARY` (2026-09-12) ≤ ex-date ≤ the ticker's last bar. FACT (live L6): 8 tickers on 2026-10-27, among them PBSA (split; `rsi_14` 22.8, `sma_50` 706.4 against close 302) and FORU (rights; `sma_50` 1,484 against close 94); 5 actions are dated after the data and are not flagged yet. (a) Flagged tickers excluded by default; (b) flagged only; (c) fix the data layer first (D22, E2); (d) price-derived cells whose lookback contains the ex-date are NA `PRICE_BREAK_IN_LOOKBACK`, the ticker flagged, flow and ADV cells kept, and an optional chip to exclude.
- **Recommendation (superseded).** Stale (a). Breaks (d), labelled TEMPORARY and paired with E2, the D22 data-layer fix, which is decided separately.
- **Decision (DECIDED, user 2026-10-28; the user's own choice).** "P4 tidak, dihide tapi di remark saat di show di filter table": stale tickers **and** tickers with a price break are **hidden by default**; when the user shows them through the filter, their rows appear in the table **with a remark** giving the reason. For stale tickers this is (a) with a remark; for price breaks it replaces (d). The rule stays TEMPORARY for price breaks, paired with E2 (the D22 data-layer fix, decided separately). It does not cover actions missing from `idx_event_annotation`, unadjusted actions before the boundary (suspected, not verified), or the Terminal, the Backtest, Feature 04 and AI answers, which stay distorted.
- **Sub-question P4.1, as asked (2026-10-28).** When a price-break ticker is shown, are its price-derived values whose lookback crosses the ex-date (A) shown with the remark, or (B) blanked with the remark? The report recommended (B): a value computed across an unadjusted break is not a reading of the stock (PBSA `rsi_14` 22.8 and `sma_50` 706.4 against close 302; FORU `bb_lower_20` negative), so under (A) a shown ticker can pass "oversold" or "far below MA50" on a distorted number, with the remark as its only warning.
- **Decision on P4.1 (DECIDED, user 2026-10-28).** (A): "P4 - pakai A" (`EXEC.md` EXEC-SCREENER: "nilai indikator yang jendelanya melewati tanggal ex tetap ditampilkan dengan remark"). The values are shown and the remark warns.
- **How the design carries it (PROPOSED; TARGET ARCHITECTURE §6.9 and §6.12, API CONTRACT §8.4-8.5, FRONTEND INTEGRATION 9.2).**
  - Two visible universe chips, on by default: "Traded on `E`" (hides stale tickers) and "No unadjusted price break" (hides flagged tickers), each with the count it hides, derived per publication (16 and 8 on 2026-10-27). Turning a chip off shows the hidden tickers; nothing is removed silently.
  - A shown ticker carries a row remark in a Remark column and on its preview, from reason codes the API returns: `STALE` with the ticker's last bar date; `PRICE_BREAK` with the action type, its ex-date, `ratio_old` / `ratio_new` and the observed close ratio. The page words them from its text table; CSV carries the code and date.
  - Under P4.1 (A), every price-derived cell of a shown price-break ticker keeps its value and its pass or fail; a cell whose lookback contains the ex-date also carries the cell remark `PRICE_BREAK_IN_LOOKBACK`, so the page marks exactly the distorted cells (the lookback rule of TARGET ARCHITECTURE §6.12: window-class outputs only while their window contains the ex-date; recursive, cumulative and calendar outputs always after it). Flow and ADV20 cells carry no cell remark (close × volume barely moves across a split).
  - Preset counts and the cross-sectional rank population (P7 a) are fixed on the default universe, so toggling a chip never moves another ticker's rank: stale and price-break tickers are outside the population; a shown ticker is ranked against that population and carries its remark (PROPOSED).
- **Impact.** Default result and preset counts exclude both groups; the universe line names what is hidden; a shown price-break ticker can match price-derived conditions on distorted values, marked by its remarks; the `actions` file must carry corporate actions in Phase 1; the run answer and CSV carry the remark codes.

#### P5. Limits on custom parameters and request complexity

- **Question.** What limits apply to custom parameters and request complexity?
- **Options.** The registry has `min: 1` and no maximum on lengths (FACT). Provisional values: caps derived from a measured cost rule (full-market cold compute at the cap ≤ budget; CCI(1000) costs 7.93 s, O(N) kernels ≤ 0.09 s); `within` ≤ 130 sessions for technical metrics; flow maxima derived from the published window; 20 conditions; 8 universe metric filters; deadline 20 s; queue 4. Final values from the Phase 17 benchmark.
- **Recommendation.** Approve them as provisional, replaced by the measured values in Phase 17.
- **Decision (DECIDED with the go, 2026-10-28).** As recommended (`EXEC.md` EXEC-SCREENER: "Keputusan lain (P5-P7, P15-P19, P21-P23) mengikuti rekomendasi laporan").
- **Impact.** The ranges shown in the UI, the refusals users can meet, and the worker's memory and thread sizing.

#### P6. Legacy technical catalogue, conventions and new indicators

- **Question.** How are the prototype's legacy technical catalogue, its conventions and new indicators handled?
- **Options.**
  - (a) Compile the 17 legacy technical entries and the 9 technical presets onto the 53 registry indicators plus transforms, with `F` conventions authoritative: EMA SMA-seeded; `volspike` excludes the current bar as in the Backtest; RVOL includes it as the registry says (user decision 2026-10-25), and its contradictory `include_current_bar` parameter stays hidden. Raw level thresholds on OBV, PVT, A/D, NVI and PVI are not offered. Ichimoku waits for a deliberate registry release (`F` + `indRegistry.json` + Backtest worker rebuild).
  - (b) Keep the prototype formulas: a second implementation; rejected.
  - (c) Add Ichimoku now in a coordinated registry release.
- **Recommendation.** (a), with Ichimoku in a later planned registry release.
- **Decision (DECIDED with the go, 2026-10-28).** As recommended (`EXEC.md` EXEC-SCREENER: "Keputusan lain (P5-P7, P15-P19, P21-P23) mengikuti rekomendasi laporan").
- **Impact.** Which presets ship in Phase 1 (Ichimoku disabled), the visible catalogue, and whether `indicators.ts` changes now (no under a).

#### P7. Population for cross-sectional ranks

- **Question.** Which population is `rs_rank` (and any cross-sectional rank) computed over?
- **Options.** (a) All active, non-stale stocks with a finite value on the evaluation date, independent of the user's filters. (b) The user's filtered universe. (c) All listings including stale ones (the prototype; NaN still in the denominator).
- **Recommendation.** (a). Ranks then do not move when filters change, can be precomputed, and are safe for the planner.
- **Decision (DECIDED with the go, 2026-10-28).** As recommended (`EXEC.md` EXEC-SCREENER: "Keputusan lain (P5-P7, P15-P19, P21-P23) mengikuti rekomendasi laporan"); with P4, stale and price-break tickers are outside the population.
- **Impact.** Minervini and CANSLIM results; planner design (the population is computed before the condition stage).

#### P8. Default board for flow, and its label toward the Backtest

- **Question.** What board do flow metrics use by default, and how is it labelled toward the Backtest?
- **Options.** (a) Regular by default (equal to price volume and to Stockbit's Foreign Flow), with an all-boards toggle; Send to Backtest is lossless only for all-board `fnet`, `broker` and `top5`. (b) All boards (Backtest and Terminal parity). (c) Regular only.
- **Context (FACT).** On 2026-10-27 the user kept all boards as the Terminal Flow default ("Untuk papan bawaan, kita tetap semua papan") and uses Regular to compare with Stockbit (ERRORS M244). The board changes the 20-day foreign net for 168 of 841 stocks and flips its sign for 20.
- **Recommendation (superseded).** (a), with the board shown on every flow condition and in the handoff. If consistency with the Terminal's default matters more than consistency with price volume and Stockbit, choose (b).
- **Decision (DECIDED, user 2026-10-28).** (b): all boards (Regular, Nego and Tunai combined) are the default for flow metrics ("Regular saja atau semua papan ... --> semua papan"), the same default as the Terminal Flow panel and the Backtest.
- **How the design carries it (PROPOSED; TARGET ARCHITECTURE §6.11).**
  - Every flow reference defaults to `board: 'all'`; a Regular variant stays available as an explicit, labelled choice (the Stockbit comparison basis, ERRORS M244), and every flow cell and handoff names its board.
  - FACT (APPENDIX B §B.2-B.3): F06 stores one row per (ticker, board, date), and a board row exists only on the dates that board traded (865 Regular, 130 Nego, 9 Tunai rows on 2026-10-27); its catalog warns "Do not compare across boards or sum across boards". So no stored per-board field is added across boards. PROPOSED: the additive one-day components (foreign and domestic buy, sell and net values, and the four frequency columns) are summed per date over the board rows present, and every multi-day or non-additive field (N-day nets, % of value, buy share, buy and sell days, z-scores and percentiles, flow vs previous window, strength, frequency ratios) is recomputed from the summed components with the F06 definitions, on the ticker's sessions.
  - The stored per-board values remain the integrity oracle: on every load the self-check compares each board's recomputed series with that board's stored F06 rows; the all-board values are sums of checked components.
- **Impact.** The flow numbers users see use the Terminal's default board (R16 closed); whether they also follow its price-bar calendar, which skips Nego-only days, is P20 (b); `fnet`, `broker` and `top5` at the default transfer to the Backtest with the same formula, and only the Regular variant is left out; values still differ for a stock with a Nego-only day in the window, which the Backtest's price-bar calendar skips (FLOW INDICATOR PROPOSALS 16.10 item 2; TARGET ARCHITECTURE §6.11). U5 now concerns only the label of the Regular variant. The z-score and percentile metrics (F5) at all boards need 252 + N sessions of the summed series, more than the 130 sessions planned for `flow_f06`; the series length is set with the flow indicator proposals (FLOW INDICATOR PROPOSALS (PHASE 2)).

#### P9. Bandar definitions and the first flow metrics

- **Question.** What are the bandar definitions, and which flow metrics ship first?
- **Options.** The bandar ratio (window D, top-N, denominator Σ buy value, thresholds 6 / 10), `bavg` (gross VWAP of the top-3 net buyers, which equals Stockbit Avg Buy, vs the prototype's typical-price proxy) and D-day breadth (buyers / (buyers + sellers)) are not approved anywhere (`verification/terminal_api/DESIGN.md:40, 147`). (a) Ship foreign net, % of value, streak, trade spike, single broker, top-5 / top-N and the stored F06 unusual-flow and strength metrics first; add bandar, `bavg` and breadth after explicit approval, sharing one definition with the Terminal detector. (b) Approve the proposed definitions now. (c) Replace them.
- **Recommendation.** (a).
- **Status (open, 2026-10-28).** Decided after FLOW INDICATOR PROPOSALS (PHASE 2) (`EXEC.md` EXEC-SCREENER: "P9, P10, P20 ... diputuskan sesudah usulan indikator flow"); its 16.11 D2 proposes the bandar definition (FL09) and "bandar average price" as FL13.
- **Impact.** Phase 2 vs Phase 3 scope, which bandarmology presets are enabled, Terminal and Screener consistency.

#### P10. Broker data lagging price

- **Question.** What happens when broker data lags price?
- **Options.** (a) Evaluate flow at the broker as-of date, show the per-cell date and a banner, and return NA `FLOW_LAGGED` beyond a user maximum (default 1 session). (b) Always NA when behind. (c) Block flow screens. Optionally, also publish the flow files after a successful stockbit round, not only at the 07:30 / 19:00 runs.
- **Recommendation.** (a). Decide the optional extra publication trigger separately.
- **Status (open, 2026-10-28).** Decided after FLOW INDICATOR PROPOSALS (PHASE 2) (its 16.11 D14 keeps (a)).
- **Impact.** Flow cell semantics in combined screens and how often flow results trail price.

#### P11. Universe filters and fundamentals without data

- **Question.** How does the Screener treat universe filters and fundamentals that have no data?
- **Options.** (a) Show market cap, index membership, listing board, notation (default switched **off**, unlike the prototype's on), free float, statement metrics and bank metrics as disabled with reasons; bank metrics `NOT_APPLICABLE` outside Banks; dividends in Phase 2 after validation, with an adjustment basis instead of a label (ERRORS D10, A3.14; AGENTS.md: a Part A gap is settled before loading): a TTM window that contains a price-affecting action is (i) NA `MIXED_ADJUSTMENT_BASIS`, or (ii) rescaled with `ratio_old` / `ratio_new` from `idx_event_annotation`; ADV = close × volume over 20 bars (the Backtest definition). (b) Hide them. Separately: give EXEC-MCAP its "go", say whether free float joins it, and choose a fundamental source and licence. Optionally, ship "High Dividend" as a labelled variant without payout.
- **Recommendation.** (a), with (i) for the dividend basis until the rescaling is validated on a sample; handle EXEC-MCAP and the fundamental source as separate items.
- **Status (open, 2026-10-28).** It confirms what stays disabled: fundamentals and market cap "menunggu data atau keputusan sendiri" (EXEC-SCREENER). Phase 1 shows these items disabled with their reasons, as (a) describes; hiding them, (b), would need the user's word.
- **Impact.** 11 of 26 presets and the market-cap column ship disabled; Phase 2 or 4 scope.

#### P12. Persistence of saved screens, My metrics and the watchlist

- **Question.** Where are they persisted, and how many watchlists?
- **Options.** (a) `edge_bff` tables now: `screener_items` with kind `screen` | `metric`, and one `watchlist_items` table, via a forward migration with `$verify$`. (b) A TEMPORARY `localStorage` adapter first, with a one-time import later. (c) Local only. Sub-questions: one watchlist or several named lists; the values of `SCREEN_LIMIT` and `WATCHLIST_LIMIT` (precedent: `PIN_LIMIT` ≤ 500).
- **Context (FACT).** The EDGE shell keeps leftover CSS for a Watchlist page (`.watchlist-page`, `apps/edge-bff/static/index.html:2494, 9106`), for a multi-list selector with a "new watchlist" button (`.watchlist-selector`, `.new-watchlist`, `index.html:8219-8286`) and for a `.nav-watchlist` nav item (`index.html:6911`). No markup, script, table or API uses them (`audit/edge_conventions.md` §3). It suggests that several named lists were once designed; nothing exists to reuse.
- **Recommendation.** (a) at the same gate, with one watchlist; (b) only if the migration is not approved.
- **Decision (DECIDED, user 2026-10-28).** (a), as recommended, with one watchlist ("P12 OK"). Still to set in Phase 1 and record in `EXEC.md`: the values of `SCREEN_LIMIT` and `WATCHLIST_LIMIT` (PROPOSED: the `PIN_LIMIT` precedent, at most 500 each). Both tables are keyed by `owner_key`, so they need no change for several users (MULTI-USER SCALE AND COST).
- **Impact.** Phase 1 includes migration 1 (`edge_bff.screener_items`, `edge_bff.watchlist_items`) with the provisioning and test changes (CHANGES AWAITING APPROVAL A6); the TEMPORARY local adapter is not built.

#### P13. Send to Backtest above the Backtest's ticker limit and for screener-only semantics

- **Question.** How does Send to Backtest handle more matches than the Backtest accepts, and semantics the Backtest lacks?
- **Options.** The limits are read from the Backtest catalog (`max_portfolio_tickers`, 12 today; `window_bars.max`, 20; `max_conditions`), never typed in the screener (TARGET ARCHITECTURE §6.15). More tickers than `max_portfolio_tickers`: (a) preselect that many by the current sort and let the user edit; (b) refuse. Window: (a) strict: send `window_bars` only when every event shares one N ≤ `window_bars.max` and there is no state or value condition, and list everything else as left out with a reason; (b) approximate with W = max N and a warning. Delivery: a page-only import in the Backtest `boot()` as EXEC-BACKTEST-LOAD rewrote it (catalog applied asynchronously, `app.ts:37-85`), with the full portable definition carried for a later Backtest release.
- **Recommendation.** Preselect by sort, editable; the strict window rule.
- **Status (open, 2026-10-28).** Phase 1b is part of the go ("Phase 1b: Send to Backtest (impor di halaman Backtest saja)", EXEC-SCREENER); these two rules are confirmed with the user before Phase 1b starts.
- **Impact.** The Backtest page change (`app.ts`, `import.ts`, `CONTRACT.md` §10) and what users see as left out.

#### P14. Screen Performance History

- **Question.** What happens to the Portfolio123-style Screen Performance History?
- **Options.** (a) Defer it and relabel the prototype view as "Stock vs IHSG". (b) A technical-only evaluator explicitly labelled non-point-in-time and survivorship-biased. (c) Wait for a Backtest engine with more than 12 tickers.
- **Recommendation.** (a), until a point-in-time universe including delisted tickers and adjusted prices (D22) exist.
- **Status (open, 2026-10-28).** The history "menunggu data atau keputusan sendiri" (EXEC-SCREENER); Phase 1 ships the relabelled "Stock vs IHSG" view of (a) and no historical evaluator.
- **Impact.** Whether any historical evaluator is built now (none under a).

#### P15. DIRE funds and unclassified stocks

- **Question.** Are the three DIRE real-estate funds (XCID, XCIS, XSPI), typed `stock/common` with sector and industry `Undefined`, part of the stock universe, and how are unclassified stocks shown?
- **Options.** (a) Include them as stocks; an unclassified stock is counted apart as "Unclassified (n)", never as a value, and an include filter keeps it only through an explicit "include unclassified" option (the Backtest's rule). (b) Exclude them by default with a visible chip, driven by a data-layer instrument type once it exists. (c) Exclude them always.
- **Context (FACT).** The publisher writes `Undefined` as "no classification, the readers' to set apart" (`apps/terminal-publisher/publisher.py:419-421`); `terminal.ts classification()` returns null for it (`apps/backtest-worker/src/terminal.ts:156`), and the Backtest catalog's `groupingsOf` counts unclassified stocks apart, "never as a value" (`catalog.ts:17-31`). ERRORS D02's lesson: "Unknown = NULL plus reason, never a fake category (A1.4)". `Undefined` covers IHSG and these three (`audit/fundamentals_universe.md` §4); XSPI is also one of the 16 stale tickers. The typing of funds as `stock` is a data-layer defect, recorded on 2026-10-28 as ERRORS D30 with its general fix: an instrument type or subtype in `IDX_Stock_Universe`, never a name list in code.
- **Recommendation.** (a) until the instrument type exists; then the universe follows the type.
- **Decision (DECIDED with the go, 2026-10-28).** As recommended (`EXEC.md` EXEC-SCREENER: "Keputusan lain (P5-P7, P15-P19, P21-P23) mengikuti rekomendasi laporan").
- **Impact.** Universe count by three; the sector list shows 11 sectors plus "Unclassified (3)".

#### P16. KVO definition (I52)

- **Question.** Which Klinger Volume Oscillator definition is approved?
- **Options.** (a) `F`'s classic Klinger with `|2(dm/cm − 1)|` (`indicators.ts:547-556`), which the registry and the Backtest already use; (b) the workbook outline without `abs`; (c) the prototype's signed-volume EMA on the hlc3 change with no dm/cm (INDICATOR MATRIX footnote 20).
- **Recommendation.** (a), shown as "definition pending" until approved; I52 is dynamic-only until then (INDICATOR MATRIX row I52).
- **Decision (DECIDED with the go, 2026-10-28).** As recommended (`EXEC.md` EXEC-SCREENER: "Keputusan lain (P5-P7, P15-P19, P21-P23) mengikuti rekomendasi laporan"): `F`'s classic Klinger is the approved I52 definition, so the "definition pending" label and the dynamic-only restriction no longer apply.
- **Impact.** Whether a registry release is needed (only under b or c, P6).

#### P17. VWAP Session anchor (I43)

- **Question.** How is I43 offered on daily bars?
- **Context (FACT).** With anchor Session on daily bars, vwap = hlc3 within 2e-16, so a Session condition reduces to close vs typical price (INDICATOR MATRIX footnote 19); the workbook marks I43's readiness `PARTIAL_LOGIC` (`audit/matrix_b.json`, I43 notes).
- **Options.** (a) Offer only the Week, Month, Quarter and Year anchors; (b) offer Session, labelled "= typical price"; (c) hide I43.
- **Recommendation.** (a).
- **Decision (DECIDED with the go, 2026-10-28).** As recommended (`EXEC.md` EXEC-SCREENER: "Keputusan lain (P5-P7, P15-P19, P21-P23) mengikuti rekomendasi laporan").
- **Consequence (PROPOSED; for the user to confirm).** I43's registry default anchor is Session (INDICATOR MATRIX row I43), which (a) no longer offers, so P21 (a) ("Default" = the registry default) gives I43 no offered default. Proposed: the I43 card has no "Default" chip and opens as Custom with anchor Week and the registry's other defaults, and the snapshot pre-warms I43 at that configuration instead of Session. The registry itself is unchanged (P6).
- **Impact.** One indicator's anchor options in the catalog.

#### P18. Historical volatility naming (I33 vs Feature 01)

- **Question.** How is I33 labelled next to Feature 01's volatility?
- **Context (FACT).** I33 is the population SD of log returns, annualized; Feature 01 `volatility_20d_ann_pct` is the sample SD of simple returns, median 2.8% and up to 23% apart (DATABASE / FEATURE CHANGES §7.3).
- **Options.** (a) Name I33 "Historical volatility (log, population)" with its unit, and never show Feature 01's value under the same name; (b) keep the workbook name.
- **Recommendation.** (a).
- **Decision (DECIDED with the go, 2026-10-28).** As recommended (`EXEC.md` EXEC-SCREENER: "Keputusan lain (P5-P7, P15-P19, P21-P23) mengikuti rekomendasi laporan").
- **Impact.** Labels and tooltips only.

#### P19. Floating ties on flat windows

- **Question.** How are exact ties decided on flat windows (for example "OBV above its SMA")?
- **Options.** (a) Raw doubles, as the Backtest (R14; FACT: running-sum residue decides BNBR's 358 of 358 disagreements); (b) an epsilon rule in a later core release shared with the Backtest.
- **Recommendation.** (a) now; (b) only as a deliberate core release.
- **Decision (DECIDED with the go, 2026-10-28).** As recommended (`EXEC.md` EXEC-SCREENER: "Keputusan lain (P5-P7, P15-P19, P21-P23) mengikuti rekomendasi laporan").
- **Impact.** Borderline cells on flat windows.

#### P20. Remaining flow and filter details

- **Question.** Four details the audit decided provisionally (APPENDIX B §B.9 items 7, 9 and 10; APPENDIX A row 10).
- **Options.** (a) Default broker for B4 and the Broker Follow preset: YP (the prototype) or YU (the Backtest default, `apps/edge-bff/backtest/src/core/catalog.ts:54`). (b) Calendar: keep two, each labelled on its cells (F06 metrics on the ticker's F06 sessions; broker metrics on its price bars, the Backtest's), or one for both (TARGET ARCHITECTURE §6.11). (c) The tickers with flow rows outside the universe (AKKU, CRAB, GTBO, TRUE, UNSP, and the ETFs): excluded and disclosed, or included in flow-only screens. (d) Whether the 53 registry indicators may be universe metric filters (the prototype offers only 8 technical, 10 flow and 32 fundamental metrics there).
- **Recommendation.** (a) YP, the prototype's default, with the broker shown on the card; (b) two calendars, labelled; (c) excluded and disclosed, counted in the refresh log (the orphan tickers are ERRORS D29); (d) yes, as VALUE filters through the same registry.
- **Status (open, 2026-10-28).** Decided after FLOW INDICATOR PROPOSALS (PHASE 2) (its 16.11 D12 and D13 carry (b) and (a)). Item (d) touches the Phase 1 metric-filter picker; the picker reads its entries from the catalog, so either answer is a catalog entry, not a code change (PROPOSED).
- **Impact.** Phase 2 flow defaults; the metric-filter picker.

#### P21. What the "Default" chip means for an unverified workbook default

- **Question.** What does a condition card's "Default" show for an indicator whose registry default the user's workbook marks as a proposed or reference profile rather than a verified UI default?
- **Context (FACT).** INDICATOR MATRIX footnote 24: only 9 indicators have every default verified (I10, I12, I13, I15, I16, I17, I30, I47, I48); the others carry PROPOSED_DEFAULT or REFERENCE_PROFILE / REFERENCE_FORMULA "not UI default" parameters, and the workbook marks the calculation readiness of I07, I09, I11, I12, I37, I43 and I52 `PARTIAL_LOGIC`. The snapshot is built at the registry defaults, which are the Backtest's.
- **Options.** (a) "Default" means the registry default, labelled with the workbook status where it is not verified ("proposed default"); (b) only verified defaults show a "Default" chip, and the others open as Custom with the registry value filled in; (c) change the registry defaults first, in a registry release (P6).
- **Recommendation.** (a): a default that differs from the registry would split the Screener from the Backtest; any change goes through the registry release (P6).
- **Decision (DECIDED with the go, 2026-10-28).** As recommended (`EXEC.md` EXEC-SCREENER: "Keputusan lain (P5-P7, P15-P19, P21-P23) mengikuti rekomendasi laporan").
- **Impact.** Chip labels; the pre-warmed configurations stay the same under (a) and (b).

#### P22. Prototype UX changes

- **Question.** Approve these changes to the prototype's UX as a set, or reject any of them individually (each is listed with its reason in FRONTEND INTEGRATION 9.2 and 9.4).
- **Options.** (1) Send to Backtest "Copy link" removed (no data in URLs; its target does not exist in EDGE); (2) the theme toggle and global search / ⌘K move to the EDGE shell; (3) Delete asks for confirmation; (4) `between` with value > value2 is refused instead of reordered; (5) bandar thresholds per condition instead of global; (6) pagination keeps the page unless rows or order change; (7) the special-notation filter defaults off; (8) `stoch` `kxd_os`: keep the coded K < 25 and correct the label "below 20", or change the test to K < 20 to match the label (APPENDIX A §A.3 #10).
- **Recommendation.** Approve (1)-(7); for (8), keep K < 25 and correct the label, so saved prototype screens keep their meaning.
- **Decision (DECIDED with the go, 2026-10-28).** As recommended (`EXEC.md` EXEC-SCREENER: "Keputusan lain (P5-P7, P15-P19, P21-P23) mengikuti rekomendasi laporan").
- **Impact.** Visible behaviour of the ported page; none of the recommended changes alters a computed number (changing `kxd_os` to K < 20 would).

#### P23. The length of "one year" and the other periods

- **Question.** How many sessions are 1M, 3M, 6M and 1Y in the Screener?
- **Context (FACT).** The prototype uses 250 for `hi52`, `lo52` and the 1Y performance view, but 252 for `rs_rank`; EDGE's user-approved fast-lane defaults use 21 for a month and 252 for a year (`apps/market-ai-orc/app/fastlane_defaults.py`, `span_month_trading_days`, `span_year_trading_days`), and I33 annualizes with 252.
- **Options.** (a) One named `periods` entry in the metric catalog with 21 / 63 / 126 / 252; (b) keep the prototype's 250 where it uses 250, recorded as the user's choice.
- **Recommendation.** (a): one definition of a year across EDGE pages.
- **Decision (DECIDED with the go, 2026-10-28).** As recommended (`EXEC.md` EXEC-SCREENER: "Keputusan lain (P5-P7, P15-P19, P21-P23) mengikuti rekomendasi laporan").
- **Impact.** `hi52`, `lo52`, the Stock vs IHSG view and presets that use them (Minervini).

### 13.3 Decisions raised after the go

PAGE LOAD SEQUENCE (6c) and MULTI-USER SCALE AND COST (6d) raised eleven decisions under provisional ids, each under "Decisions for the user"; their final ids are P24-P34, the same numbers ("P24-new" there is P24 here, and so on). Each is **PROPOSED** and open. The options, the evidence and the recommendation are in those sections; the summary:

| # | Decision | Recommendation (from the raising section) | Scope |
|---|---|---|---|
| P24 | May the page draw its last catalog, universe and result from the browser cache before the server confirms them? | (a) yes, only after the first authenticated answer of the page load, marked "Updating…" until confirmed | Screener page, Phase 1 |
| P25 | Framed pages wait for the chat's model list before the frame is created | Measure first; if it costs more than 100 ms on a cold open, render frame routes once the session answers | EDGE shell, outside the Screener phase |
| P26 | The 473 KB shell document is downloaded uncompressed and `no-store` on every open | Settle whether Railway's edge compresses first; then compress in edge-bff and revalidate the shell scripts | EDGE-wide, outside the Screener phase |
| P27 | One session/CSRF helper for every framed page, or a third copy | (b) a third copy now, a shared module as a later clean-up | Screener page, Phase 1 |
| P28 | Page-load targets | Accept the targets of 6c.7 as the acceptance criteria of the Screener page | Screener page, Phase 1 |
| P29 | Who the "many users" are: a small trusted team, external users or subscribers, or both in stages | State the expected number of daily users and of users at once, so the scaling triggers and the cost table (6d.9-6d.10) are set from them; the Screener's design is the same for all three | Input for P31-P33 and the EDGE-wide items |
| P30 | EDGE user accounts | Keep one owner for Screener Phase 1 (the Screener is keyed by `owner_key` and needs no change later); a user directory in `edge_bff` as its own EXEC item before a second person uses EDGE | EDGE-wide, outside the Screener phase |
| P31 | terminal-api identity per user and a service account for the workers (it replaces the TEMPORARY quota override) | One terminal account per EDGE user plus one service account for `backtest-worker` and `screener-worker`, together with P30's user directory | EDGE-wide, outside the Screener phase |
| P32 | Availability floor of `screener-worker` | One replica on dev in Phase 1; two replicas from the first day other people use it (about USD 6 a month more) | Screener, Phase 1 (dev) and later |
| P33 | Per-user compute limits | Fair sharing only (per-owner lanes, the per-request budget) until P29 is answered; a per-user CPU budget if external users come | Screener, Phase 1 |
| P34 | Shared result cache across replicas | Per-replica caches; revisit only if S22 shows repeated custom screens across replicas dominating CPU | Screener, Phase 1 |

The flow indicator choices of FLOW INDICATOR PROPOSALS (PHASE 2) keep their own list (16.11) and settle P9, P10 and P20. MULTI-USER SCALE AND COST also lists EDGE-wide needs under its own labels E1-E6 (6d.8); they are not the CHANGES AWAITING APPROVAL items E1-E5 (14.6), which are proposals in `FUTURE_PLAN.md`.


## CHANGES AWAITING APPROVAL

Every change the Screener makes, grouped by phase, with the decision it rests on, its risk and its rollback. The heading keeps the approval-gate name; the go has been given (below). All deployments are to **dev** only (`lucid-patience` / dev); nothing goes to production. Deploys run outside the publisher windows 00:00-01:00 and 12:00-13:05 UTC (ERRORS M250), and a deployment is claimed only when its exact deployment reaches SUCCESS (AGENTS.md). Labels and evidence notation as in TARGET ARCHITECTURE.

**Status: approved, Phase 1 in execution (FACT, `EXEC.md` EXEC-SCREENER).**
- 2026-10-27: read-only audit and pushes to the session's working branch (the approval history, moved from `PLAN.md` SCREENER).
- 2026-10-28: the go for execution phase by phase on dev ("Arti gas maksudnya tetap jalankan sesuai fase, take into account jawaban saya diatas (P1-P4 dan P12)"), with P1, P2, P3, P12 (a), P4 with sub-choice A and P8 (all boards) decided by the user, and P5-P7, P15-P19 and P21-P23 following the recommendations.
- Still needed: P13 before Phase 1b; P9, P10, P20 and the flow indicator choice before Phase 2; each item of 14.5 and 14.6 its own approval. Production is never part of this work.

### 14.1 Phase 0: branch only (no new approval needed)

| ID | Change | Risk | Rollback |
|---|---|---|---|
| Z1 | Screener core, overlay, generator, unit / property / parity / drift tests on local data, on the working branch | None to running services (nothing deployed) | Delete the branch |
| Z2 | Tripwire script and parity script (read-only DB use through pgweb only) | None | — |
| Z3 | Documentation on the branch: the ERRORS entries of DATABASE / FEATURE CHANGES §7.5 (done 2026-10-28: D24-D30, C09-C11, M255-M261, R41-R42, D22 and D23 updated; commits `270dde5`, `ad7ba34`); the approval words and P1-P23 in `PLAN.md`, then moved with the go to `EXEC.md` EXEC-SCREENER (done, `88d3344`); E1-E5 in `FUTURE_PLAN.md` (done, `514057e`); this report as `verification/screener/AUDIT.md` (to commit) | None (documents only); they reach `main` only with an approved merge | Revert the commit |

### 14.2 Phase 1: technical screener on dev (go given 2026-10-28; P1-P7, P12, P15-P19, P21-P23 decided; in execution)

| ID | Change | Decision | Risk | Rollback |
|---|---|---|---|---|
| A1 | terminal-publisher writes `v1/xsection/price.<sha16>` and `actions.<sha16>` (the existing `ref/tickers.json.gz` is reused), indexes them in `state.json`, carries the index forward in other modes, prunes unreferenced objects. CLI deploy under the M248 procedure (TARGET ARCHITECTURE §6.17) | P1 | A longer run (one 2 s statement, about 14 MB more upload, INFERENCE); a bug could break the run that also feeds Terminal and Backtest; a branch upload without the latest main could overwrite newer publisher work (M248) | Redeploy the previous publisher deployment (CLI); the new objects become unreferenced and are deleted by key. `state.json` without `xsection` stays valid for every reader. FACT (main `010af1e`): terminal-api's `Bucket.state()` returns only `STATE_FIELDS` (`bucket.py:45-53`) and the backtest worker reads only `finished_at` and `broker_through` (`terminal.ts:595-603`, `catalog.ts:42`) |
| A2 | terminal-api: extend the existing `GET /state` (live since terminal-api `689dc465`, `main.py:297-305`; any subscriber, no grant) with an additive `xsection` field (`bucket.py:8` `STATE_FIELDS`, and its test), and add `POST /xsection` for proxy-key callers only, logged under `REF` (no migration). CLI deploy under the M248 procedure | P1 | A mistake on `/xsection` could expose a large file to a direct subscriber; `/state` is read by the backtest worker's catalog (`catalog.ts:38-43, 58-81`), and an additive field does not change it; a branch upload without main `6f318ea` would remove `/state` (M248) | Redeploy terminal-api `689dc465` (the current deployment); edge-bff does not call these routes, and the Backtest reads only `/state`'s existing fields |
| A3 | Optional: additive `packs: {name: {sha256, bytes}}` field on `/manifest`, so the worker can compare pack sha256 values | — | Low: readers ignore unknown fields (`apps/backtest-worker/src/terminal.ts:575-590` at `010af1e`) | Redeploy the previous terminal-api deployment |
| A4 | New Railway service `screener-worker` (1 replica, `sfo`, private only, memory 2 GB to start), its variables (names: `SCREENER_WORKER_KEY`, `TERMINAL_URL`, `TERMINAL_PROXY_KEY` by reference, `SCREENER_FILE_ORIGIN`, `SCREENER_THREADS`, `SCREENER_CACHE_BYTES`, `SCREENER_CACHE_DIR`; limits with no defaults: `SCREENER_MAX_CPU_MS`, `SCREENER_CAP_BUDGET_MS`, `SCREENER_DEADLINE_MS`, `SCREENER_MAX_CONDITIONS`, `SCREENER_MAX_METRIC_FILTERS`, `SCREENER_WITHIN_MAX`, `SCREENER_MAX_COUNTS`, `SCREENER_MAX_RESPONSE_BYTES`, `SCREENER_QUEUE`, `SCREENER_MAX_FILE_BYTES`, `SCREENER_MAX_INFLATED_BYTES`, `SCREENER_MAX_REFRESH_BYTES`, `SCREENER_OWNER_INFLIGHT`, `SCREENER_PREVIOUS_GRACE_S`), Railway healthcheck `/ready`, no volume, deploy from GitHub `main` with watch patterns; more threads first, then replicas, on the triggers of MULTI-USER SCALE AND COST 6d.10. Created through a pinned IaC plan (ERRORS R29): `railway config pull --force` first, then `railway config plan --verbose --out`, applied with `railway config apply --plan` only if its changes are this service and the edge-bff `SCREENER_*` variables (TARGET ARCHITECTURE §6.17) | P3 | One more service; a shared-core change redeploys it; Railway may skip a merge commit (ERRORS M252); a plain apply would also apply unrelated drift (the R05 legacy services, which it would redeploy; backtest-worker's builder) | Remove the service or set it to 0 replicas; edge-bff then answers `SCREENER_UNAVAILABLE`, or `SCREENER_DISABLED` once its URL is unset |
| A5 | edge-bff: `app/screener.py` routes, the `/screener` sub-app and shell tab, the Dockerfile stage, `SCREENER_WORKER_URL` / `SCREENER_WORKER_KEY` variables; deploy from GitHub `main` | P3 | The edge-bff image and the shell change for every EDGE page; pinned tests must be updated | Revert the merge commit and redeploy; unsetting `SCREENER_WORKER_URL` alone switches the feature off (`SCREENER_DISABLED`) |
| A6 | Migration 1: `edge_bff.screener_items`, `edge_bff.watchlist_items`, exact grants, `$verify$`; `scripts/provision_edge_bff_login.py`, `tests/conftest.py` | P12 | Schema change on the EDGE database schema; the provisioning script refuses until updated | Rollback body in the migration comment (`DROP TABLE` ×2) and revert the provisioning change; no other table is touched (P12 a is decided, so the TEMPORARY local adapter is not built) |
| A7 | `.railway/railway.ts` and `RAILWAY_CHANGELOG.md`: `railway config pull --force` before the change (the edge-bff `EDGE_TERMINAL_URL` and `TERMINAL_PROXY_KEY` set live on 2026-10-25 enter the file, ERRORS R41); the pinned plan reviewed, its only changes the screener ones, the pre-existing drift (R05 legacy services, backtest-worker builder, ERRORS R42) named and left out; the plan recorded; then `railway config pull --force` and `railway config plan` after the change | — | Applying unrelated drift redeploys legacy services (R05); IaC drift if skipped | Revert the files |
| A8 | Phase 17 benchmark on dev, including concurrency 8 and screens during a Backtest job; the page timings of PAGE LOAD SEQUENCE 6c.9 after each deploy; the multi-user scenarios of MULTI-USER SCALE AND COST | P5, P28 | Load on dev services during the runs | Stop the driver |
| A9 | Optional: a GitHub Actions workflow on PRs touching the screener-worker watch paths, running `check_backtest_untouched.mjs`, backtest-worker `npm test` and `npm run registry:check`, the Terminal calc tests and the screener core tests (the general fix for R7, TEMPORARY until then) | — | CI minutes; a flaky test blocks a PR | Delete the workflow file |

### 14.3 Phase 1b: Send to Backtest (part of the go; P13 confirmed before it starts)

| ID | Change | Risk | Rollback |
|---|---|---|---|
| B1 | Backtest page: `boot()` reads and deletes the one-shot import key; new `src/import.ts`; page tests. Prerequisite: read `BACKTEST_END_TO_END.md` and `apps/edge-bff/backtest/CONTRACT.md` in full, then update both (CONTRACT §10) | Touches the Backtest page `boot()` as EXEC-BACKTEST-LOAD rewrote it (asynchronous catalog, `app.ts:37-85`), not its core or worker; tested with an early and a late catalog (M253 lesson) | Revert the page commit; the worker and core are untouched, so Backtest results do not change |
| B2 | Shell `postMessage` navigation listener (`edge-nav`, same origin and own frame only) | A listener that accepted other origins would allow navigation by any page | Revert the shell commit |

### 14.4 Phase 2: flow (P8 decided: all boards; needs P9, P10, P20 and the indicators chosen from FLOW INDICATOR PROPOSALS (PHASE 2))

| ID | Change | Risk | Rollback |
|---|---|---|---|
| C1 | Migration 2: NOLOGIN group `terminal_publisher_feature_reader` with SELECT on `Feature_06_Foreign_Domestic` (optionally `Feature_04_Technical_Indicator`), granted to `terminal_publisher_login` only; `scripts/provision_terminal_logins.py` reach update. FLOW INDICATOR PROPOSALS 16.10 proposes SELECT on `Feature_03_Stock_Broker_Daily` instead of, or beside, Feature 06 for the long all-board series (its D9) | Widens what the publisher login can read | Rollback body in the migration comment (`REVOKE`, `DROP ROLE`); revert the provisioning change |
| C2 | Publisher writes the flow files with the completeness gate: `flow_f06` (130 sessions as designed; longer for the all-board percentile metrics) and `broker_window` (41 complete sessions as designed), their sources and lengths set by the chosen indicators (FLOW INDICATOR PROPOSALS 16.9-16.10) | INFERENCE: about 10-40 s more DB time per publication on a 128 MB buffer pool shared with the AI; the exact per-date statements measured read-only with bounded `EXPLAIN (ANALYZE, BUFFERS)` before this go (NEXT ACTION 15.1), confirmed at the first run | Redeploy the previous publisher; the worker marks flow unavailable when the files are absent |
| C3 | The flow indicators the user picks from FLOW INDICATOR PROPOSALS (PHASE 2) (FL01-FL20; 16.8 recommends a first set of 11), on all boards by default (P8), and the flow presets that need no bandar definition; the audit's starting set F1-F8, B1, B4, D1, D4 (TARGET ARCHITECTURE §6.11) is superseded by that choice | Flow lags price without a new Stockbit token (R4) | Disable the flow items in the catalog (availability `REQUIRES_DATA`) |
| C4 | Dividend yield TTM and years of dividends, after an independent validation sample | Wrong yields if amounts are not as expected (U8) | Disable the two metrics |
| C5 | Optional `f04` reconciliation file | None to results (logging only) | Stop writing the file |

### 14.5 Phase 3 and later (each its own approval)

| ID | Change | Needs | Risk | Rollback |
|---|---|---|---|---|
| D1 | Bandar ratio, `bavg`, D-day breadth, shared with the Terminal detector | P9 definitions | Unvalidated thresholds | Disable the items |
| D2 | Ichimoku (and any new indicator) through a registry release: `indicators.ts`, `indRegistry.json`, regenerated `backtest-registry.json`, backtest-worker rebuild and redeploy | P6 (c) or later | A Backtest change: `registry_version` changes, and the worker exits until rebuilt (`apps/backtest-worker/src/server.ts:349` at `010af1e`) | Revert the release and redeploy the previous worker |
| D3 | Market cap (EXEC-MCAP parts A/B) and, if chosen, free float | EXEC-MCAP "go" | Licence risk noted in `EXEC.md` (EXEC-MCAP) | As in EXEC-MCAP |
| D4 | A fundamental data source and its onboarding | P11, source and licence | New data domain; point-in-time rules (A2.7) | Per onboarding plan |
| D5 | Screen Performance History | P14 and a point-in-time universe with delisted tickers | Survivorship and look-ahead if built early | — |

### 14.6 Related items outside the Screener (raised by the audit; each needs its own approval)

| ID | Change | Risk | Rollback |
|---|---|---|---|
| E1 | Rack schedule change (a publication right after the price cron), if fresher evening data matters (P1) | More publisher runs; the backtest worker rebuilds its catalog on each new `finished_at` (`catalog.ts:58-81`), and the screener-worker its snapshot | Restore the cron |
| E2 | Data-layer fix for unadjusted splits and rights (ERRORS D22; it retires the TEMPORARY price-break rule of P4): re-pull or rescale a ticker's history on the corporate action | Rewrites price history; Feature 04 recalculation of the affected suffix ends `REPAIR_REQUIRED` per ticker without a manual repair | Per D22 plan |
| E3 | Swap `Sector` / `Industry` back in `Universe_Equity_Description` (ERRORS D23) | Readers of that table (AI backend tool list) change | Swap again in one transaction |
| E4 | Sequence the planned 2026-09-17/18 price refill with a Feature 04 repair (about 840 tickers would end `REPAIR_REQUIRED`, ERRORS D26), and fix the IHSG abort in `backfill.py` and `bootstrap_states.py` (ERRORS D27) | Feature 04 outage until repaired | Per Feature 04 runbook |
| E5 | Feature 04 heap density (4.36 rows/page; ERRORS D28). Root cause SUSPECTED, not dead tuples: FACT (live, 2026-10-28) `n_dead_tup` 4,775 of 1,386,130, last autovacuum 2026-10-11; about 21 rows of 359 B would fit per page; INFERENCE: free space left by the 2026-10-11 full-table rewrites, already vacuumed and reusable (check: `pg_stat_user_tables`, `relpages` vs `reltuples` × width). `VACUUM FULL` or `pg_repack` would help multi-day scans only; latest-date scans are slow because rows are clustered by ticker (about one row per page, `audit/verify_feature04.json` additional findings), which they do not change. General fix at the owning layer: a bulk-rewrite procedure (a new-table swap, or batched rewrites with `VACUUM` between batches) for the next Feature 04 VERSION bump, Feature 01 or broker feature refresh | `VACUUM FULL` takes an exclusive lock on a 2.5 GB table | — |

### 14.7 Hard constraints and definition of done

The brief's nine hard constraints, each with the design element that enforces it and the test that checks it (PROPOSED).

| Hard constraint (do not …) | Design element | Enforcing test |
|---|---|---|
| Rebuild the 53 formulas independently in multiple services | I1: one `F`, through `Calc.out(key, resolveParams(...))`; the worker imports `indicators.ts` | A test fails if a screener file defines an indicator kernel (TARGET ARCHITECTURE §6.1); tripwire (TEST PLAN 10b.9); bundle test: no formula code in the page (10b.12) |
| Calculate all indicators for every ticker on every request | One snapshot per publication (§6.7) plus the planner (§6.10) | Planner property test (10b.6); run log `conditions[].tickers_evaluated`; S1 and S5 (PERFORMANCE BENCHMARK PLAN 11b.3) |
| Send all IDX OHLCV to the browser for full-market screening | Server-computed screens and preview; `/state` and `/xsection` absent from the browser allow-list; `connect-src 'self'` | Bundle test (10b.12); relay and route tests (10b.11) |
| Query large raw PostgreSQL tables for every user request | No DB credential in the worker; the publisher reads once per publication | The worker's variable list holds no database variable (§6.17; config test); column D of 11b.3 is non-empty only for S8 and S15 |
| Silently substitute a different formula | I1, I7 and the narrow-only rule; every changed operator listed with its reason (§6.9.1) | Formula parity (10b.1); narrow-only, narrowing probes and operator coverage (10b.10) |
| Silently change Feature 04 historical semantics | I4: Feature 04 unchanged, a parity oracle only | Tripwire over `features/feature04/**` and `apps/feature-04-worker/**`; Feature 04 pytest, 49 passed (10b.9) |
| Silently use today's fundamental data for historical screens | No historical evaluator (P14); fundamentals disabled with reasons; "today only" (§6.12, §6.13) | Every disabled item carries a reason (10b.12); D5 needs its own approval (14.5) |
| Break the existing Backtest worker | I3: no byte change in its code, registry or core | Tripwire, backtest-worker `npm test` and `npm run registry:check` (10b.9); S20; its deployment ID unchanged in the dev E2E (10b.13) |
| Deploy directly to production | Dev only (this section's header; the go is for dev, EXEC-SCREENER) | Each deploy step names dev and the exact deployment ID at SUCCESS (NEXT ACTION 15.2) |

The brief's definition of done, item by item:

| Item | Where it is shown |
|---|---|
| Universe filters work | TEST PLAN 10b.5; dev E2E 10b.13 |
| The 53 indicators have an approved calculation path | §6.8 contract; 10b.1, 10b.10 |
| Defaults preferentially use verified precomputed data | Snapshot pre-warm checked against Feature 04 (10b.1, 10b.2) |
| Custom parameters calculate dynamically | 10b.2 (direct call and Feature 04 at its stored non-default configurations) |
| Feature 04 reused according to the approved architecture | P2; parity oracle (10b.1, 10b.2) |
| Formulas versioned and auditable | `versions` in every answer (API CONTRACT §8.3); `snapshot_digest`; `F04_PARITY.md` (10b.10) |
| Match logic correct; near misses work | 10b.6 |
| Event dates correct | `within` boundaries (10b.3); every event date checked against the bars (10b.13) |
| Sorting and pagination work | 10b.12 page behaviour |
| Result values explain why each ticker passed | Cells with value, dates and reason (§8.5); 20-ticker independent recompute (10b.13) |
| Stock preview works; chart data is real | Preview bars equal the Terminal's (10b.13) |
| Saved screens follow the approved persistence decision | P12; 10b.11 owner filter and migration; reload in 10b.13 |
| CSV export works | 10b.12; 10b.13 |
| Send to Backtest loses no condition or parameter | 10b.8 (losslessness, round trip of the full `definition`, limits) |
| No synthetic market data in the production flow | Bundle test: no fixture code in production (10b.12) |
| Full-market screening benchmarked | PERFORMANCE BENCHMARK PLAN; A8; `BENCHMARK.md` |
| The Backtest worker remains intact | 10b.9; deployment ID unchanged (10b.13) |
| No production deployment without approval | This section's header; NEXT ACTION 15.2 |

The user's requirements of 2026-10-28 add two acceptance items to this list: the page-load targets of PAGE LOAD SEQUENCE 6c.7 (P28), measured by its timing script (6c.9), and the scale and cost criteria of MULTI-USER SCALE AND COST.


## NEXT ACTION

Labels and evidence notation as in TARGET ARCHITECTURE. Steps are **PROPOSED** unless marked done (FACT, with the commit or record that shows it).

**Status: approved, Phase 1 in execution** (FACT, `EXEC.md` EXEC-SCREENER, 2026-10-28: the go "Arti gas maksudnya tetap jalankan sesuai fase, take into account jawaban saya diatas (P1-P4 dan P12)"; "Status 2026-10-28: dimulai"). The go is for dev, phase by phase. The decisions in force are in 15.3 and UNKNOWNS / PRODUCT DECISIONS 13.2.

### 15.1 Done before and with the go (FACT)

1. **ERRORS entries** for the audit's defects (AGENTS.md Part D: the task that finds a defect records it), recorded on 2026-10-28 in commits `270dde5` and `ad7ba34`: D24-D30, C09-C11, M255-M261, R41-R42; D22 (FORU, the derived count of 8 price-affecting actions, the Screener's TEMPORARY rule) and D23 (844 of 844 rows consistent with a swap, 841 differ) updated in place (DATABASE / FEATURE CHANGES §7.5). Still to update when Phase 1 lands: D22's Solution, which names the per-cell NA rule that P4.1 (A) replaced by values with remarks; a note in M250 that the xsection family is its first content-addressed application.
2. **Proposals E1-E5** in `FUTURE_PLAN.md` (commit `514057e`). ERRORS D22, D23 and D26-D28 do not link to them yet.
3. **Approval, answers and go** recorded, and the item moved from `PLAN.md` SCREENER to `EXEC.md` EXEC-SCREENER (commit `88d3344`; AGENTS.md "Plans", R34).
4. **Phase 1 started on the branch**: the sub-app scaffold and a draft wire contract under `apps/edge-bff/screener/` (commit `8a236eb`, "foundation in progress; no deploy").
5. **This report**: to be committed as `verification/screener/AUDIT.md`, with the evidence files listed for commit.

### 15.2 Phase 1 on dev, in order

Branch work first (no deploy):

1. **Screener core and contract** in `apps/edge-bff/screener/src/core/` with the overlay, the generator (`--check`) and the unit, property, parity and drift tests of TEST PLAN §10b.1-10b.6 and §10b.10, on local data.
2. **Isolation checks** before every push: `scripts/screener/check_backtest_untouched.mjs`, backtest-worker `npm test` and `npm run registry:check`, Terminal calc tests, Backtest page tests, Feature 04 pytest (49). Outputs recorded.
3. **Read-only parity** with `scripts/screener/parity_f04.py` through pgweb (SELECT only), recorded in `verification/screener/F04_PARITY.md`.
4. **Bit-parity test** of `F` on typed views (settles U2).
5. **Read-only plan evidence** (AGENTS.md "Performance"): bounded `EXPLAIN (ANALYZE, BUFFERS)` with literal bounds, through pgweb, of the exact whole-universe price statement (Phase 1), recorded for `DATABASE_CHANGELOG.md`. The per-date flow statements (Feature 06 and Feature 05 as designed, or Feature 03 as FLOW INDICATOR PROPOSALS 16.10 proposes) are measured the same way before the Phase 2 go (settles U6).
6. **Code for the other parts, tested locally:** publisher xsection writer and terminal-api routes with their tests; `screener-worker`; `app/screener.py`; the page port with fixture mode, its load sequence (PAGE LOAD SEQUENCE 6c.4-6c.6) and its late-data smoke (6c.9); the multi-user design of MULTI-USER SCALE AND COST; local E2E with a fixture worker and a fixture terminal-api. Migrations written and exercised first on a disposable test database (`EDGE_TEST_POSTGRES_URL`).

Then on dev:

7. **Read before changing** the publisher and terminal-api routes the Backtest reads: `BACKTEST_END_TO_END.md` (now with §17) and `apps/edge-bff/backtest/CONTRACT.md`, in full (AGENTS.md), and update them in Phase 1 (end-to-end §4, §5, §6 and §11; CONTRACT [D-L3]). The `/state` route already exists (EXEC-BACKTEST-LOAD, `EXEC.md:8444-8462`); the change is one additive field (`xsection` in `STATE_FIELDS`), built on the merged code at main `010af1e` or later.
8. **Inspect live state** before any mutation, with the explicit project, environment and service IDs from `PROJECT_CONTEXT.md`: Railway services and deployments; the database roles, grants and `edge_bff` tables.
9. **Migration 1** (P12 a, decided): DRYRUN, then apply on dev; read back tables and grants, run `$verify$`, update the provisioning script, append `DATABASE_CHANGELOG.md` and `APPLIED.sha256`.
10. **terminal-api** (CLI, the M248 procedure: merge the latest main into the branch, fetch main right before the upload and again after SUCCESS, upload the repository layout with `git archive`, compare the live build with the merged tree; or merge to main first and deploy the merge commit): deploy the `/state` extension and `/xsection`; claim it only at the exact deployment's SUCCESS; check that `/state` still answers the backtest worker (its catalog `flow.data_through` unchanged) and now carries `xsection`, and that `/xsection` refuses a call without the proxy key and answers one with it; append `RAILWAY_CHANGELOG.md`, noting that a branch deploy can be overwritten.
11. **terminal-publisher** (CLI, the same M248 procedure): deploy outside the M250 windows; run one manual publication (clear the cron schedule, `railway up` a new deployment, restore the schedule; `publisher.py:17-21`); check the xsection objects and the `state.json` index; record `EXPLAIN (ANALYZE, BUFFERS)` of the new statements.
12. **Merge to `main`** for `screener-worker` and edge-bff. Create the `screener-worker` service on dev through a pinned IaC plan (ERRORS R29): `railway config pull --force` first; `railway config plan --verbose --out <file>`; apply with `railway config apply --plan <file>` only if its changes are the new service and the edge-bff `SCREENER_*` variables, with the pre-existing drift (R05 legacy services; the backtest-worker builder, ERRORS R42; the edge-bff variables missing from the file, ERRORS R41) named in the review and left out of the apply; record the plan in `RAILWAY_CHANGELOG.md`. Check that the merge commit itself was deployed (ERRORS M252); claim each deployment only at SUCCESS.
13. **Verify the worker:** `/ready`, the refresh log line (files, bytes, integrity, `snapshot_digest`), and live parity of the snapshot with Feature 04 on the same date.
14. **Switch on edge-bff:** set `SCREENER_WORKER_URL` / `SCREENER_WORKER_KEY`; check the tab, catalog, a run and a preview, and the universe chips with their counts (P4).
15. **Real-data E2E on dev** per TEST PLAN §10b.13, recorded in `verification/screener/E2E.md` with deployment IDs and the publication's `finished_at`; the page timings of PAGE LOAD SEQUENCE 6c.9 in `verification/screener/PAGE_TIMING.md`.
16. **Phase 17 benchmark** per PERFORMANCE BENCHMARK PLAN, with the concurrency scenarios of MULTI-USER SCALE AND COST; set the limits and the memory from the rules; record `verification/screener/BENCHMARK.md` and the variable changes (names only) in `RAILWAY_CHANGELOG.md`.
17. **Onboarding document** (the user's requirement 3; EXEC-SCREENER "dokumen onboarding"): how the Screener works and how to add an indicator or a data source (technical, flow, fundamental, macro), with the PostgreSQL requirements and the per-service checks. Written separately from this report.
18. **Close the loop:** update `.railway/railway.ts`, run `railway config pull --force` and `railway config plan`; update `PROJECT_CONTEXT.md`, READMEs, the catalogs that apply, and the ERRORS statuses and wording of 15.1 item 1; `git diff --check`; commit; push `main`; verify the branch matches `origin/main`. If the push fails, report the task as incomplete.
19. **Report** the verified Screener workflow with evidence, then repeat the same pattern for Phase 1b (Send to Backtest, on the Backtest page as EXEC-BACKTEST-LOAD left it) and Phase 2 (flow, migration 2).

### 15.3 Decisions in force and still open

- **In force (DECIDED by the user, 2026-10-28):** P1 (a) the rack; P2 (a) Feature 04 unchanged, defaults recomputed in memory; P3 (a) `screener-worker` from GitHub `main`; P4: stale and price-break tickers hidden by default and shown with a remark, with P4.1 (A) their values shown with the remark; P8 (b) all boards for flow; P12 (a) the `edge_bff` tables with one watchlist.
- **In force with the go, as recommended:** P5, P6, P7, P15, P16, P17, P18, P19, P21, P22, P23.
- **Before Phase 1:** none; Phase 1 has started.
- **During Phase 1, to confirm:** P24, P27 and P28 (raised by PAGE LOAD SEQUENCE) and P32, P33 and P34 (raised by MULTI-USER SCALE AND COST), built to their recommendations unless the user decides otherwise (UNKNOWNS 13.3); P29, the expected number of users, which sets the scaling triggers and the cost table; the consequence of P17 for I43's default anchor (UNKNOWNS 13.2, P17). P25, P26, P30 and P31 are EDGE-wide items outside the Screener phase.
- **Before Phase 1b:** P13.
- **Before Phase 2:** P9, P10 and P20, decided after FLOW INDICATOR PROPOSALS (PHASE 2) together with its own choices (16.11: which indicators, windows, board exceptions and the publisher's read source for migration 2).
- **Confirming what stays disabled:** P11 (fundamentals, market cap) and P14 (screen performance history).
- **Asked, not decisions:** U7, U9 and U12.


## APPENDIX A — PROTOTYPE UI TO BACKEND MAPPING

**Sources.**
- The prototype is the user's upload `screener EDGE layout.html`, 1,717 lines (not committed; named in `EXEC.md` EXEC-SCREENER, moved from PLAN.md SCREENER).
- Line numbers below are prototype lines. They come from the two audits `audit/html_ui.md` and `audit/html_model.md`, with the verifiers' corrections; the corrections changed few UI lines.
- The catalog was extracted by running prototype lines 562-1115 in an isolated Node `vm` with no DOM and no network: `evidence/html_ui/catalog.json`, `evidence/html_model/catalog.json`, `evidence/html_model/presets_resolved.txt`.
- Evidence notation as in the header: `audit/<area>.md` and `audit/verify_<area>.json` (reports and verifications), `evidence/<area>/<file>` (raw outputs), all relative to `verification/screener/`; repository `path:line` citations are at `main` `010af1e`.

**Labels.**
- FACT: seen in code, data or a measurement.
- INFERENCE: concluded from facts.
- PROPOSED: a recommendation.
- UNKNOWN: not established.

**Classification codes** (the brief's five classes):

| Code | Meaning |
|---|---|
| **S** | Already supported: an existing endpoint or published data already delivers it to an EDGE page. |
| **I** | Requires integration: the data exists; it needs wiring or an endpoint. |
| **C** | Requires calculation: derived values must be computed server- or client-side. |
| **N** | Requires new data: not in the market database. |
| **D** | Requires a product decision. |
| client | Pure browser behaviour on data already loaded. Counted as **Already supported** (S) for the brief's five classes: no backend requirement; the page code is part of the frontend port (FRONTEND INTEGRATION). |

**Prototype facts that frame every row (FACT).**
- The prototype is one standalone page with no network calls. All data is synthetic and built in the browser: 94 tickers, 400 weekday sessions to 2026-10-23, a synthetic IHSG, synthetic fundamentals and broker nets (l.559-735).
- It re-evaluates every condition over every ticker on every edit (`refresh` l.1698 → `compute` l.1178).
- The catalog has 115 entries: 53 registry indicators (`x_*`, I01-I53), 17 legacy Technical, 13 Flow, 32 Fundamental.
- All 26 presets use only legacy keys, never an `x_*` key.
- Ten indicators exist twice (RSI, Stochastic, MACD, ADX, Bollinger, ATR, Supertrend, MFI, CMF, OBV). `audit/html_model.md` counts 11 legacy re-implementations, adding `volspike`, which is not equal to registry `rvol`.

---

### A.1 Control and feature mapping

**Decisions taken since the audit (FACT, UNKNOWNS / PRODUCT DECISIONS; the D class below records what needed a decision at the audit).** Persistence (rows 17, 25, 44, 61): P12 (a), `edge_bff` tables, one watchlist. Notation filter (rows 9, A.3 #30): shown disabled, default off (P11 a, P22 item 7). Stale tickers and price breaks, which the prototype has no notion of (the row 9 proxy): hidden by default, shown with a remark (P4, P4.1 A). Flow board (rows 5 and the flow presets): all boards (P8 b). Near-miss rule (row 32): one rule (TARGET ARCHITECTURE §6.9). Theme, search, delete confirmation, `between`, pagination (rows 26, 41, 63, 64; A.3 #7, #10): P22 as recommended. Rank population (A.3 #22): P7 (a). Still open: the default broker, the calendar, the orphan tickers and registry indicators as metric filters (P20; row 10 and the `follow` preset), the bandar definition (P9; row 56), the market-cap buckets and fundamentals (P11; rows 1, 4, 7, 8, 53), Send to Backtest (P13; row 62), the performance history (P14; row 51).

#### A.1.1 Universe

| # | Control / feature | Code reference | What it needs | Class | Label and evidence |
|---|---|---|---|---|---|
| 1 | Index quick filter and drawer section (LQ45 / IDX30 / IDX80 / ISSI, with counts, OR across choices) | `usec` 1266; `inUniverse` 1161 | Effective-dated index membership per ticker (point-in-time for any history) | **N**, **D** (which indexes) | FACT: no such column in any schema (`evidence/fundamentals_universe/column_search.txt`) |
| 2 | Sector include / exclude (3-state chips) | 1269, 1471 | `IDX_Stock_Universe."Sector"`: 11 IDX-IC sectors + `Undefined` (4 rows: IHSG, XCID, XCIS, XSPI). Backtest catalog groupings already deliver it. | **S** | FACT: all 11 prototype sector names exist in the DB; counts in `evidence/fundamentals_universe/universe_counts.txt`; `contract.ts:320-336` |
| 3 | Industry checklist | 1272 | `IDX_Stock_Universe."Industry"`: 58 real values + `Undefined`. The list must come from data. | **S** (list from data) | FACT: only 14 of 31 prototype industry labels exist in the DB (`evidence/fundamentals_universe/proto_vs_db.txt`). Do not use `Universe_Equity_Description`: its Sector and Industry are swapped (ERRORS D23, OPEN). |
| 4 | Market cap min/max and buckets (Mega ≥ 200 T, Big 50-200, Mid 10-50, Small 1-10, Micro < 1) | 1167-1168; `CAPB` 1257 | Shares outstanding × close, on the same split basis | **N** (planned), **D** (bucket bounds) | FACT: no column. EXEC-MCAP (EXEC.md 8152-8270) plans it and waits for "go"; Part A would cover 820 of 844 stocks, with no history. |
| 5 | Liquidity: ADV ≥ Rp B (default 1) | `advOf` / `fixedCond('adv')`; 1141, 1170 | 20-session mean of close × volume from the price table; or exact traded value from F03/F06 | **C**, **D** (definition, board, days without a bar) | FACT (verifier): over 20 sessions close × volume differs from the exact Regular value by median 0.67%, p90 2.57%, max 15.3%; 2 stocks cross the 1 B threshold (TEST EVIDENCE T9) |
| 6 | Price ≥ Rp (default 50) | 1141 | Last final close per ticker | **I** (trivial **C**) | FACT: 83 stocks close < 50 |
| 7 | Free float ≥ % | `t.F.freeFloat` | Float shares ÷ shares | **N**, **D** | FACT: none. A TradingView `float_shares_outstanding` field was seen but is not in the EXEC-MCAP column plan (EXEC.md 8167-8169, 8207-8211). |
| 8 | Board: Main / Development | `t.board` | Listing board per ticker | **N**, **D** | FACT: `market_board` is the **trading** board (Regular / Nego / Tunai) and must not be used |
| 9 | "Exclude special-notation / FCA stocks" (default **on**; the chip cannot be removed) | 1141, 1275 | Special-notation / FCA flags | **N**, **D** | FACT: no source. As shipped, the default-on filter would be a silent no-op (`audit/fundamentals_universe.md` FU15). "No bar on the last session" (16 stocks) is a suspension proxy, not notation (INFERENCE). |
| 10 | Metric filters in the drawer (`>`, `<`, between), default "ROE > 10" | 1274, 1487 | 8 Technical, 10 Flow and 32 Fundamental metrics; the 53 registry indicators are excluded | **C** (technical, flow), **N** (fundamental), **D** (default metric; whether to allow registry indicators: P20 d) | FACT: `evidence/html_ui/catalog.json` `metricFilterOpts` |
| 11 | Active-filter chips, "Clear all", "In universe X of N" | `scopeChips` 1243; 1286 | Universe count after filters | **C** | FACT |
| 12 | Quick-filter popover (focus, Clear, Done, live count) | `renderPop` 1296; `QCLEAR` 1295 | Universe count | **C** / client | FACT; see defect A.3 #3 |
| 13 | Universe evaluation order: index, board, sector in/out, industry, cap, price, ADV, free float, notation, metric filters | `inUniverse` 1160-1174 | A query planner over the same predicates | **C** | FACT |

#### A.1.2 Presets and match mode

| # | Control / feature | Code reference | What it needs | Class | Label and evidence |
|---|---|---|---|---|---|
| 14 | Preset category tabs (All, Bandarmology, Technical, Fundamental, Combined, My screens); chips with the "why" tooltip; overflow row with the active chip in front | `presetsHtml` 1206; `fitPresets` 1217 | Static preset definitions; rebuilt on real metric keys | **I**, **D** (keep legacy keys or rebuild presets on the registry) | FACT |
| 15 | Preset match-count badges ("Stocks that match today") | `libCounts` 1187: at boot (1713), after a bandar-threshold edit (1628), after save, delete or duplicate (1455, 1456, 1651) | A whole-universe result per preset per as-of date | **C**, **D** (show counts? cache per data date) | FACT. INFERENCE (verifier): this is the strongest argument for precomputing the fixed flow grid or the preset counts (APPENDIX B, B.8). |
| 16 | Load a preset; clicking it again clears the conditions and keeps the universe | `openSource` 1197 | — | client | FACT |
| 17 | My screens chips: Duplicate (adds `′`), Delete (no confirmation), tooltip "n conditions · saved <data date>" | 1206, 1453-1456 | Persistence | **D** (browser or server), **N** (schema, if server) | FACT: `localStorage['edge-screens']`. No server table exists in any schema (`audit/edge_conventions.md` 3.1). |
| 18 | Match All / Any / At least N ("of n active"), shown when ≥ 2 conditions | `needOf` 1177 | Per-condition pass flags; met and need per ticker | **C** | FACT: equal to Backtest `entryNeed` (conditions.ts:263) |

#### A.1.3 Screen builder

| # | Control / feature | Code reference | What it needs | Class | Label and evidence |
|---|---|---|---|---|---|
| 19 | Collapse toggle with summary "n active conditions · m of U pass" | `renderConds` 1341 | Pass count per condition over the universe | **C** | FACT. The per-condition pass count is computed but never rendered (A.3 #4). |
| 20 | Type-ahead adder with synonyms; "/" shortcut; ↑ ↓ Enter Esc | `drawSuggest` 1365; 1407 | Catalog: the 53-indicator registry plus a flow and fundamental catalog | **S** (53 technical), **D** (flow and fundamental list; the 10 duplicates) | FACT: `backtest-registry.json`; `terminal/src/data/indRegistry.json` |
| 21 | Quick-add rail (Browse all, RSI, Stochastic, MACD, Supertrend, Bollinger, RVOL, Bandar status, ROE) | empty state | Same catalog | **S** / **D** (Bandar and ROE need flow and fundamental decisions) | FACT |
| 22 | Indicator browser dialog: groups with counts, listbox, details (registry id, defaults, conditions, "Starts as") | `openBrowser` 1417; `drawBrowser` 1433 | Registry metadata and descriptions | **S** / **D** | FACT |
| 23 | Condition card: colour dot, name, enable switch, remove, summary text | `condRow` 1318; `condText` 1069 | Re-run the screen | **C** / client | FACT |
| 24 | Default / Custom segmented control; parameter grid with "default X" hints; changed fields highlighted | 1318; `isDefP` / `isCustom` 1148-1149; `resetParams` 1384; `applyField` 1489 | Custom parameters → dynamic calculation from OHLCV; a validation contract | **C**, **D** (validation) | FACT: the prototype rounds step-1 numbers, ignores values ≤ 0 and has no min/max. `XPARAM` (l.864) carries no min/max, sends booleans as strings and lists three parameters the registry refuses: `adr.timeframe`, `rvol.reference_method`, `rvol.include_current_bar`. `registry.ts resolveParams` refuses wrong types and never rounds (`audit/html_model.md` 2.4). |
| 25 | "Save as My metric" (name ≤ 40 characters; same name replaces; linked cards rename or unlink) | `openSaveMetric` 1385-1404; `syncMetric` | Persistence | **D** | FACT: `localStorage['edge-metrics']` |
| 26 | Operator select, value test: `gt`, `lt` (strict), `between` (inclusive, bounds reordered) | `evalCond` 1062-1067 | Last-bar value; a new `between` operator | **C** | FACT: the core has no `between` (conditions.ts:25). An empty v2 is read as 0 (`+''`). Decided with the go: `value > value2` is refused, not reordered (P22 item 4). |
| 27 | Level cross `xa` / `xb` "within N sessions" | 1065 | Full series; a per-condition window; crossings scanned only over the last 130 bars | **C** | FACT: the cell shows the current value, not the cross date |
| 28 | Custom states (68 entry/op pairs, e.g. "Close above SMA", "In uptrend", "+DI above −DI", "SMA rising vs 5 sessions ago") | 1057-1058 | Last-bar state; some need lagged or cross-instance comparisons | **C** | FACT: counts from `evidence/html_ui/catalog.json`. Gaps are in REUSABLE BACKTEST COMPONENTS, section 5.4. |
| 29 | Custom events (65 pairs, e.g. golden cross, Supertrend flip, MACD cross, bullish divergence, squeeze) "within N", shown as "today" / "Nd ago" | 1059-1061 | Event date and sessions ago per condition | **C** | FACT: N has no maximum (`n = max(1, n\|0)`). The Backtest window is 1-20. |
| 30 | Operator totals | — | — | — | FACT: 109 gt, 109 lt, 101 between, 43 xa, 38 xb, 68 custom state, 65 custom event; 96 distinct custom labels (`evidence/html_ui/catalog.json`) |

#### A.1.4 Results

| # | Control / feature | Code reference | What it needs | Class | Label and evidence |
|---|---|---|---|---|---|
| 31 | Meta line: "N matches · meet all/any/at least k of n · U in universe"; "pick a preset" when empty; "filtered by q" | `renderResults` 1518 | Match counts | **C** | FACT |
| 32 | Near-miss switch, near rows (`near` pill), "Near misses n" | 1180; 1549 | Count-based near miss: met = k − 1, only with > 1 condition and k > 1 | **C**, **D** (count only or a numeric distance; fix the inconsistency in A.3 #1) | FACT |
| 33 | Results search `#tq` (symbol or company substring; Esc and × clear) | 1518 | Ticker and company names | **S** (catalog names), client | FACT: `catalog.tickers[].name` |
| 34 | Columns Symbol, Company, Sector (colour tag) | 1518 | Catalog | **S** | FACT |
| 35 | Columns Last and 1D | 1518 | Last two final closes | **I** / **C** (trivial) | FACT |
| 36 | Column Mkt cap (and the tie-break of every sort) | 1507-1510 | Market cap | **N** | FACT: sort ties break on market cap, descending |
| 37 | Column Avg value 20D (tooltip "Average daily traded value, 20 sessions") | 1518 | ADV | **C** | FACT |
| 38 | Column Met (dots + m/n) | 1518 | met / active count | **C** | FACT |
| 39 | One column per active condition: header with dot, short name and parameter pill (highlighted when custom); tooltip with rule and parameters; value text; failing cells greyed | 1518; `condText` 1069 | Per condition: value, pass, event age, n/a | **C** | FACT |
| 40 | Sorting: default `match desc` (`met + 100·match`); a new key starts desc except Symbol (asc); matches above near rows; nulls last | `sortedRows` 1507 | All rows of one scan in one answer | client (+ **N** for the market-cap tie-break) | INFERENCE: ~844 rows fit one answer (a 5-value result is 37 KB gzip, PERFORMANCE EVIDENCE 11.5) |
| 41 | Pagination 10 / 25 / 50 / 100 (default 25), "Showing a-b of n", previous / next | 1518 | — | client | FACT: any edit returns to page 1 (A.3 #7) |
| 42 | Row selection, "select all" (current page only), bulk bar (N selected; Add to Watchlist; Send to Backtest; Export CSV (selected); Clear) | 1518 | — | client | FACT: selection survives paging and is cleared by `loadState` |
| 43 | Empty states: Clear search; "Show near misses (n)"; "Match at least n − 1"; Reset universe | 1549 | — | client | FACT |
| 44 | Watch toggle per row; bulk "Add to Watchlist" | 1515-1516 | Watchlist persistence | **D**, **N** (schema, if server) | FACT: `localStorage['edge-watchlist']`, read once at load. EDGE has no Watchlist page, table or API (`audit/edge_conventions.md` 3.1). |

#### A.1.5 Detail panel, preview and chart

| # | Control / feature | Code reference | What it needs | Class | Label and evidence |
|---|---|---|---|---|---|
| 45 | Head: two-letter logo (colour from a hash), ticker, sector tag, company, close | `renderDetails` 1590 | Optional real logo | **I** (optional) | FACT: `/api/terminal/v1/logo/{ticker}` exists (main.py:35) |
| 46 | Quote: last close, "±x% today", status pill (Outside universe / In universe / Match m/n / Near m/n / m/n) | 1590-1599 | Price + scan result for the ticker | **I** / **C** | FACT: the pill's near rule differs from the table's (A.3 #1) |
| 47 | Line "industry · board · index memberships" | 1590 | Industry (S); board and indexes (N) | **S** / **N** | FACT |
| 48 | Chart / Performance segmented control | 1590 | — | client | FACT |
| 49 | Preview chart: candles of the last 130 sessions; overlay lines per active condition (12 registry overlays + legacy `price_ma`); `arrowUp` markers on event bars; static; no volume, panes or IHSG | `drawChart` 1608-1615 | One ticker's OHLCV through the existing per-ticker `/bundle` path; overlays and markers from the shared core | **I** + **C** | FACT: the Backtest page already runs this chain (REUSABLE BACKTEST COMPONENTS, section 5.6). `lightweight-charts` 5.2.1 is pinned in both apps. |
| 50 | Performance view: stock vs IHSG rebased to 100 over 1M / 3M / 6M / 1Y (21 / 63 / 126 / 250 sessions), "Outperformed / Underperformed IHSG by x pts" | `perfCard` 1581-1589 | Published IHSG; the same maths as Terminal "Relative performance" (stats.ts:263-281) | **I** | FACT. Align IHSG by date: IHSG has 2 dates no stock has (2026-09-17/18). |
| 51 | "Screen performance history (Portfolio123-style)" as titled | comment 1575 | Point-in-time universe and membership, historical evaluation of every condition, rebalance and holding rules, costs, delisted stocks | **D**, **C**, **N** | FACT: not implemented. The code draws only the selected stock vs IHSG. It has no rebalancing, holding rule, historical universe or aggregation. INFERENCE: reading it as "how this screen performed" is hindsight and survivorship bias. |
| 52 | "Why it passed / did not pass" list (dot, text, value, ✓ / ✕) | 1590 | Per-condition results for the ticker | **I** / **C** | FACT |
| 53 | Fundamentals facts: Market cap, P/E (n/m when loss-making), P/B, ROE, Div. yield, EPS growth, D/E ("bank" for banks), Piotroski | 1604 | Fundamental data | **N** (dividend yield derivable, **C**) | FACT (APPENDIX C) |
| 54 | Copy: "TK Name · price" plus one "✓/✕ condText → value" line per condition, to the clipboard | 1629 | — | client | FACT |
| 55 | Send to Backtest from the panel (the single picked ticker) | 1630 | See row 62 | **D**, **I** | FACT |
| 56 | Method & sources view: preset context; **editable global bandar thresholds** (acc ≥ %, big acc ≥ %), saved with screens; "How conditions work"; sources; sample-data note | `renderMethod` 1617-1628 | Approved flow definition and thresholds | **D**, **C** | FACT: `BANDAR = {acc:4, big:10}` (781) is reset to 6/10 (1082). Editing re-runs every bandar condition and every preset count. |
| 57 | Empty panel: "Pick a stock — click a result row or look up any ticker at the top" | 1590 | — | client | FACT: the search it points to is hidden (row 63) |
| 58 | Responsive drawer at ≤ 900 px (max 380 px); `sizePreview` | CSS 526; 1540 | — | client | FACT |

#### A.1.6 Page head, export, save, top bar and cross-cutting behaviour

| # | Control / feature | Code reference | What it needs | Class | Label and evidence |
|---|---|---|---|---|---|
| 59 | Screen name input, source pill (Preset · cat / My screen / Custom screen, "· edited"), data line "IDX equities (94 sample listings) · close <date>" | `renderHeader` 1225 | `data_through` | **S** | FACT: backtest `catalog.data_through` |
| 60 | Reset | 1225 | — | client | FACT |
| 61 | Save screen / Save changes (same name replaces; stores `{name, date: <data date>, state: snapshot()}`) | `openSave` 1644-1653; `snapshot` 1643 | Persistence of universe, conditions, logic, atLeast, sort, nearMiss and bandar thresholds | **D** (browser, server or both), **N** (schema if server) | FACT: `localStorage['edge-screens']`, keyed by name |
| 62 | Export menu → Send to Backtest dialog: Single / Portfolio mode; per-condition table ("Entry rule", "Screen only — it chose the tickers", "Screen only — not in the Backtest catalog"); Download JSON; Copy link; Open in Backtest | `openSend` 1674-1693; `toBacktest` 1655-1673 | An import entry in the Backtest page; at most 12 tickers; the wire contract | **D**, **I** | FACT: the target `backtest.html#import=<base64>` does not exist in EDGE. 13 legacy keys are mapped, none of the 53. Details in REUSABLE BACKTEST COMPONENTS, section 5.7. |
| 63 | Global ticker search `#gq` (8 hits, "Match" / "Stock" tags) and ⌘K / Ctrl+K | 1632-1638 | Ticker list (**S**) | **D** | FACT: the header is `hidden` (531). EDGE's shell has its own "Search markets — coming soon" button and ⌘K. |
| 64 | Theme toggle (`edge-scr-theme`) | 1710-1712 | EDGE shell theme: `localStorage edge-auth-monitor-theme`, applied as `html.dark` | **I**, **D** | FACT: no iframe app reads the shell theme today |
| 65 | Nav: Analytics (disabled), Watchlist (disabled), Screener | 532-533 (hidden) | EDGE shell nav entry, page component and route | **I** | FACT: about ten touch points (index.html, edge-labels.js, main.py) |
| 66 | Export → Export results (CSV); bulk "Export CSV (selected)" | `exportCsv` 1565 | Rows already loaded | client | FACT: file `<name-slug>-<last date>.csv`. Columns: Symbol, Name, Sector, Industry, Last, 1D %, Market cap (IDR T), Avg value 20D (Rp B), Status, Met, then one per condition. All visible rows on every page. The "selected" export uses universe order, not sort order. |
| 67 | Export → Duplicate as new screen (in memory) | 1240 | — | client | FACT |
| 68 | Export → Method & sources | 1240 | — | client | FACT |
| 69 | Tooltips: 28 `title=` uses (preset why, count badge, disabled nav, condition description, Default/Custom, enable switch, remove/duplicate/delete, column headers, Avg value, watch, cap buckets, Browse, Close, previous/next, builder summary) | various | Text only | client | FACT: no custom tooltip component |
| 70 | Toast (2.2 s) | `#toast` | — | client | FACT |
| 71 | Keyboard: `/` focuses the adder; Esc closes menu → dialog → popover → drawer → preview; ↑ ↓ Enter in the adder and browser; Enter commits the title | 1407 and others | — | client | FACT |
| 72 | Accessibility present: `role=dialog` (5), tab/tablist, listbox/option; `aria-expanded`, `aria-pressed`, `aria-selected`; `:focus-visible` | — | — | client | FACT. Gaps in A.3 #9. |
| 73 | State transitions: `refresh(level)` (all / universe / universe-light / conds / conds-light) always recomputes `R = compute()`, sets page = 1 and re-renders header and results; number inputs debounce 350 ms; an identical value is ignored; `MEMO` caches every series and is never evicted (except bandar keys) | 1698-1699; 1489-1503; 776-777, 1203 | A request model: which edits call the server, debouncing and cancellation | **C**, **D** | FACT (code). INFERENCE: with server-side screening, each edit becomes a request. The edge-bff "latest wins" relay pattern applies. |
| 74 | Boot: theme icon → `libCounts()` (26 presets + saved screens) → preview closed → `loadState(empty)` → `refresh('all')`; loading a preset with the preview open picks the first match | 1709-1717; `repick` 1201 | Preset counts at load | **C**, **D** | FACT |
| 75 | Browser storage keys `edge-screens`, `edge-metrics`, `edge-watchlist`, `edge-scr-theme`, all wrapped in try/catch | `store` 1136 | — | **D** | FACT. INFERENCE: `edge-*` is the EDGE shell's namespace on the same origin, so a port should use another prefix (`audit/edge_conventions.md` 3.2). |
| 76 | Delivery: inline `<script>` and a vendored 197 KB Lightweight Charts 5.2.1 | 551-559 | A sub-app build with external scripts only | **I** | FACT: the sub-app CSP is `script-src 'self'` with no `'unsafe-inline'` (main.py:39-48). INFERENCE: the inline scripts would be blocked there. |

---

### A.2 The 26 presets

**Conventions.**
- Conditions are as coded (`evidence/html_model/presets_resolved.txt`). Every preset uses logic "all"; `n` is the "within" window.
- "Data now" says whether every input exists in live data today:
  - **Yes**: all inputs exist; calculation code is still needed.
  - **Partial**: some inputs exist.
  - **No**: blocking data is missing.
- **No preset runs in EDGE today**, because no screener code exists (FACT).

| id | Name | Category | Conditions (as coded) | Universe / sort | Data needed (real source) | Data now |
|---|---|---|---|---|---|---|
| bigacc | Big Accumulation | Bandarmology | bandar(days 10, top 3) bigacc [state]; price_ma(20, SMA) above [state] | sort c0 desc | Broker ranking from F05 (not stored; formula approval needed); SMA20 = F04 `sma_20` | **Yes** (+ **D**: bandar formula) |
| fstreak | Foreign Accumulation Streak | Bandarmology | fstreak > 4; fnet(20) > 0 | c0 desc | Streak from F06 `foreign_net_1d` (calculation); `foreign_net_20d` stored per board | **Yes** (board: all boards, P8 b, decided) |
| silent | Silent Accumulation | Bandarmology | silent(5, 20, 1.3, 4) on [state]; bandar(10, 3) > 0 | — | Price close and volume; broker ranking | **Yes** (+ **D**) |
| freq | Frequency Spike | Bandarmology | freq(20) crosses above 2.5 within 3; ret(1) > 0 (today) | c0 desc | F06 trade count (`foreign_buy_freq_1d + domestic_buy_freq_1d`), last 24 sessions; `return_1d` | **Yes** |
| bavg | Near Bandar Average Price | Bandarmology | bavg(10) between −3 and 3; bandar(10, 3) acc [state] | — | F05 `buy_value`, `buy_lots` of the top-3 D-day net buyers; close | **Yes** (+ **D**: gross VWAP vs the prototype's typical-price proxy) |
| follow | Broker Follow | Bandarmology | broker(YP, 5) > 1 (Rp B); price_ma(50, SMA) above | c0 desc | F05 one broker over 5 sessions; F04 `sma_50` | **Yes** (+ **D**: default broker YP vs Backtest YU, P20 a; board: all boards, P8 b, decided) |
| minervini | Minervini Trend Template | Technical | price_ma 150 above; price_ma 200 above; ma_cross(150, 200) above; price_ma 200 rising (vs 21 bars); ma_cross(50, 150) above; price_ma 50 above; lo52 > 30; hi52 > −25; rs_rank(252) > 70 | universe advMin 5 | SMA 50/150/200 (only `sma_50` is in F04); 250-bar high/low (F04 stores no high/low); cross-sectional RS rank | **Yes** (+ **D**: rank population). FACT: 8 stocks priced on 2026-10-27 have < 200 bars, so SMA200 is null for them. |
| brk52 | 52W Breakout + Volume | Technical | breakout(250) up within 3 [event]; volspike(20) > 1.5 (today, not on the breakout day) | — | Price; core `breakout` and `volspike` exist | **Yes** |
| oversold | Oversold in Uptrend | Technical | price_ma(200, SMA) above; rsi(14) < 40 | c1 asc | SMA200 (compute); F04 `rsi_14` | **Yes** |
| golden | Golden Cross | Technical | ma_cross(50, 200, SMA) golden within 20 | — | Price; core `macross golden_cross` | **Yes** |
| macddiv | MACD Bullish Divergence | Technical | macd(12, 26, 9) bdiv within 10 | — | Price; core `bullishDivergence` (same algorithm) | **Yes** |
| rebound | Rebound on Bullish Trend | Technical | price_ma 50 above; price_ma(10) crossed above within 3 [event]; price_ma 20 above; volspike > 1.3 | — | Price (SMA10 is not in F04) | **Yes** |
| squeeze | Bollinger Squeeze Breakout | Technical | bb(20, 2, 120) squeeze within 15; bb brk within 5 (the "then" order in the text is not enforced) | — | Price; bandwidth rolling minimum (new calculation); F04 bands | **Yes** |
| stflip | Supertrend Flip | Technical | supertrend(10, 3) flip within 5; adx(14) > 20 | — | `F.supertrend`; F04 `adx_14` | **Yes** |
| ichi | Ichimoku Bullish | Technical | ichimoku(9, 26, 52) above [state]; tenkan crosses kijun within 10 | — | Price; Ichimoku is **not** among the 53 (new indicator) | **Yes** (+ **C**: new formula) |
| graham | Graham Defensive | Fundamental | pe < 15; grahamRatio < 1; der < 1; divYears > 4; epsG3y > 0 (the text's "P/B < 1.5" has no condition) | — | Statements; dividends for divYears | **No** (1 of 5 derivable) |
| piotroski | Piotroski F-score ≥ 7 | Fundamental | piotroski > 6; pb < 3 | c0 desc | 2 fiscal years of statements; book value | **No** |
| magic | Magic Formula (Greenblatt) | Fundamental | magicRank < 21 | capMin 5; exclude Financials; c0 asc | EV, EBITDA/EBIT, ROIC, market cap; rank population | **No** (only the sector exclusion) |
| quality | Quality Compounder | Fundamental | roe > 15; der < 0.8; netMargin > 10; epsG3y > 8 | — | Statements | **No** |
| dividend | High Dividend | Fundamental | divYield > 5; payout < 85; divYears > 4 | c0 desc | `idx_event_annotation` DIVIDEND + price (derivable); payout needs net income | **Partial** (2 of 3) |
| garp | GARP | Fundamental | peg < 1; epsG > 15; roe > 12 | — | Statements | **No** |
| deep | Deep Value | Fundamental | pb < 1; 0 ≤ pe ≤ 10 | — | Statements | **No** |
| bank | Bank Quality | Fundamental | roe > 12; npl < 3; car > 18; casa > 60 | industries [Banks] | Bank reports | **No** (universe of 48 banks exists) |
| canslim | CANSLIM-lite | Combined | epsGq > 20; epsG3y > 10; hi52 > −20; rs_rank(252) > 70; roe > 12 | — | Statements + price + cross-section | **Partial** (technical half only) |
| qflow | Quality + Foreign Inflow | Combined | roe > 15; der < 1; fnet(20) > 0; price_ma 50 above | — | Statements + F06 + price | **Partial** (flow and technical half). The flow audit listed only "fnet(20) > 0 + fundamentals"; corrected by `audit/verify_flow.json`. |
| vacc | Value + Accumulation | Combined | pb < 1.5; pe < 12; bandar(10, 3) acc | — | Statements + broker ranking | **Partial** (flow half only) |

**Totals (FACT for data, INFERENCE for readiness).** 15 presets have all their data (6 Bandarmology, 9 Technical). 4 are partial (High Dividend, and the 3 Combined). 7 are blocked by missing fundamental data. The 6 Bandarmology presets also wait on flow formula, board and threshold decisions (APPENDIX B).

**Note (FACT).** Every Bandarmology and Combined flow preset uses a fixed parameter grid: bandar(10, 3), bavg(10), broker(YP, 5), fnet(20), fstreak, freq(20) crossing within 3, silent(5, 20, 1.3, 4) (`audit/verify_flow.json` additional findings).

---

### A.3 Prototype defects and inconsistencies found

| # | Defect | Code reference | Label and evidence |
|---|---|---|---|
| 1 | The near-miss rule differs between the table (`A.length > 1 && k > 1 && met === k−1`) and the detail pill (`met === k−1` with no guard). A single failing condition, or a stock under ANY, shows "Near 0/n". | 1180 vs 1599 | FACT |
| 2 | "Clear all" calls `freshUniverse()`, which brings back the ADV ≥ 1 and Price ≥ 50 chips, so two chips remain | 1243, 1141 | FACT |
| 3 | Two liquidity clears disagree: the chip × sets advMin, priceMin and ffMin to 0; the popover's Clear restores 1 / 50 / 0 | `QCLEAR` 1295 | FACT |
| 4 | The per-condition pass count is computed on every render but never shown: `updateCondsLight` looks for `[data-pass]`, which no markup creates | 1318 | FACT |
| 5 | Unreachable code: `paramUI` (1353) and its `data-pb/psum/hb/preset`, `data-pedit` and `act 'tqclear'` | 1353 | FACT |
| 6 | Parameters must be > 0 and step-1 fields are rounded silently, so registry-legal zeros (factor, multiplier, weights, `band_1_multiplier`, `volume_scale`, `initial_value`, `constant`) cannot be entered. No maximum is applied, while the registry caps `std_dev` at 50. | 1489-1497 | FACT |
| 7 | Any edit returns the table to page 1 | `refresh` 1699 | FACT |
| 8 | "Select all" selects only the visible page; the "selected" CSV export uses universe order, not sort order | 1518, 1565 | FACT |
| 9 | Accessibility gaps: no `aria-modal`, focus trap or focus return after dialogs or the drawer; no `aria-live` on the toast; no `aria-sort`; result rows are not keyboard-reachable (tabindex count 0), and a row click is the only way to open a preview; no arrow keys on `role=tab` segments; no text alternative for the chart | — | FACT (attribute counts excluding line 557) |
| 10 | `stoch` `kxd_os` tests %K < 25 while its label says "below 20" | 806 | FACT |
| 11 | `x_kvo` is a signed-volume EMA on the change in hlc3, not Klinger's volume force: about 99% of scale off, often with the opposite sign. Three KVO definitions disagree: `F`, the xlsx outline and the prototype. | 966 | FACT |
| 12 | `x_hist_vol` uses sample SD (×1.026 vs `F`'s population SD). Feature 01 `volatility_20d_ann_pct` uses sample SD of simple returns: three conventions exist. | 944 | FACT |
| 13 | `x_rvol` excludes the current bar by default, against the user decision of 2026-10-25 (EXEC.md:7881; INDICATOR_SPEC I37). Legacy `volspike` also excludes it, as the Backtest `volspike` does. | 948, 828 | FACT |
| 14 | `x_obv` starts at 0 instead of V[0] (constant offset). Prototype A/D is **not** a difference: it equals `F` and TA-Lib (the verifier refuted the matrix_b claim). | 951; 958 | FACT (`audit/verify_matrix_b.json`) |
| 15 | `x_psar` start and reversal conventions differ (direction differs on 12-104 of 250 bars). `x_supertrend` tests against the previous final band (1-22 differing bars over a full history). | 918 (psar); 909 (supertrend) | FACT |
| 16 | Flat-window conventions differ from `F`: `x_kama` (ER = 0 on a zero path), `x_stoch_rsi`, `x_cci` (running-sum residue: DADA 66.67 vs 0), `x_cmo` (0 vs null), `x_ultimate_osc` (NaN). RSI differs in long flat stretches (DADA, 48.14 vs 0). | 901-930 | FACT |
| 17 | `x_hma` rounds √n where `F` floors it, so it differs at custom lengths (length 15: 1.2e-2) | 901 | FACT |
| 18 | Code-level differences found by the verifier: ATR / NATR bar-0 TR = H − L with first value at bar 13 (890, 767; the curated "ATR %" at 816 uses the same `ATR()`); Chaikin SMA-seeded EMAs (960); MFI `q‖1e-9` (771); EOM 0 instead of null at V = 0 (963); VWAP returns the source price when the period volume is 0 (956); %B null where `F` gives 0.5 on residue-width bands; no zero-denominator guards for I31 and I38 | as listed | FACT (`audit/verify_matrix_b.json` b-prototype-engine-differs) |
| 19 | There are two indicator engines, `XI` (866-968) and a legacy helper set (753-777: EMA seeded with a[0], MACD signal over NaN → 0, RSI `l‖1e-9`, STOCH with 50-filled warm-up, ATR running mean with bar-0 TR). Every Technical preset runs on the legacy set. | 753-777 | FACT (`audit/verify_matrix_a.json` additional findings) |
| 20 | Donchian: the value uses the unlagged band, while its states and events use the lagged band. In `F`, a generic `close > upper` can never be true (0 hits market-wide). | 1025-1027 | FACT |
| 21 | The "N-session average" of cumulative indicators is an EMA (EMA 20 for OBV/PVT/A/D, EMA 255 for NVI/PVI), although the label says "average". EMA-based states are start-dependent (TEST EVIDENCE T4.5). | 1046 | FACT |
| 22 | `rs_rank` and `magicRank` ignore the user's universe; NaN returns still count in the `rs_rank` denominator. The `magic` preset applies capMin after ranking, so fewer than 20 rows can remain. Magic ranks by EV/EBITDA, where Greenblatt uses EBIT/EV. | 827, 855, 1104 | FACT |
| 23 | Preset texts claim tests the code does not run: graham "P/B < 1.5"; squeeze "then"; brk52 volume "on" the breakout day; stflip and minervini "≥" coded as ">" | 1091-1110 | FACT |
| 24 | `toBacktest` maps none of the 53 `x_*` keys. It sends bandar acc/bigacc/gt as `top5 > 0` (ratio, thresholds and N dropped) and `topacc` as `top5` whatever its `top` parameter. It drops stoch %D, maps only SMA versions of `price_ma` / `ma_cross`, and can send more than 12 tickers to a page with no import entry. | 1655-1693 | FACT (`audit/verify_flow.json` row corrections S3 rows 1-2) |
| 25 | `BROKERS` (667) flags YP (Mirae) as domestic (0), while `IDX_Broker_Profile` has YP as `Foreign`, Retail-heavy. All 14 prototype broker codes exist in the profile. | 667 | FACT (`audit/verify_flow.json` row correction; the flow audit had cited line 572) |
| 26 | `topBrokers` (785) and `bandarStatus` (784) are defined but never called | 784-785 | FACT |
| 27 | The synthetic foreign flow is built from the **next** 3 sessions' returns (look-ahead), so flow presets look predictive on the sample data | 699-700 | FACT |
| 28 | The synthetic IHSG is a cap-weighted mean of the 94 sample tickers using today's market caps as fixed weights | 710 | FACT |
| 29 | The "Screen performance history (Portfolio123-style)" comment heads code that only draws one stock vs IHSG | 1575-1588 | FACT |
| 30 | The notation filter defaults to on with no notation data (a silent no-op on real data) | 1141, 1275 | FACT |
| 31 | The global search, ⌘K target, theme toggle and nav are in a `hidden` header, yet the empty-panel text tells the user to "look up any ticker at the top" | 531; 1590 | FACT |
| 32 | Sample data does not match the database: WIKA is absent from the universe and price tables; 62 of 93 sample prices differ by > 25%; SIDO's sector and 17 of 31 industry labels differ from the DB | 573-666 | FACT (TEST EVIDENCE T10) |
| 33 | Marker collection runs for every evaluated ticker, while only the selected ticker is drawn (wasted work) | 1060, 1066 vs 1614 | FACT (`audit/verify_flow.json` row correction "S3 evaluation note") |
| 34 | `MEMO` is never evicted, except bandar keys | 776-777, 1203 | FACT |


## APPENDIX B — FLOW / BANDARMOLOGY MAPPING

**Sources.**
- Flow audit: `audit/flow.md`, read 2026-10-27 19:33-19:50 UTC.
- Adversarial verification: `audit/verify_flow.json`, re-read 19:50-20:03 UTC. Its refutations and row corrections are applied below and marked "(corrected)".
- Raw evidence: `evidence/flow/` and `evidence/verify_flow/`. Evidence notation as in the header: `audit/<area>.md` and `audit/verify_<area>.json` (reports and verifications), `evidence/<area>/<file>` (raw outputs), all relative to `verification/screener/`; repository `path:line` citations are at `main` `010af1e`.
- Prototype lines refer to the user's upload `screener EDGE layout.html` (1,717 lines, not committed).

**Labels.**
- FACT: seen in code, data or a measurement.
- INFERENCE: concluded from facts.
- PROPOSED: a recommendation; the flow audit's own metric design is audit input to the design, not an approved design.
- UNKNOWN: not established.

**User context (FACT, brief follow-up, verbatim).** *"Indikator flow, feel free untuk benchmark dan come up with your own screener lah ya. Retaining existing screener juga tidak apa."*
- UNKNOWN (verifier): what "existing screener" means is open (check: ask the user; UNKNOWNS U9).
  - The flow audit reads it as the Backtest flow conditions `fnet`, `broker` and `top5`.
  - In the user's approval (`EXEC.md:8505-8510`, EXEC-SCREENER, the history moved from PLAN.md SCREENER) the sentence follows the flow remark, so it may equally mean the prototype's own flow screens and presets.
  - No screener exists in the repository (FACT: `audit/verify_flow.json` C17).
  - Ask the user.

---

### B.1 Prototype flow metrics → source, class and match

**Class values.**
- **Existing source**: read a stored column as is.
- **Precomputed feature**: a stored Feature column with the same formula and grain.
- **Dynamic**: computed per request from stored daily rows.
- **Unavailable**: no data.

"Snapshot" marks a metric that the flow audit proposes to precompute (B.7).

**How the prototype evaluates flow conditions (FACT, prototype `evalCond` 1055-1068; verifier corrections applied).**
- States and value tests (gt / lt / between) read the last bar only.
- Crossing operators exist only for `fnet` (xa / xb), `broker` (xa), `freq` (xa), `mfi` / `cmf` (xa) and `obv` "high". Each tests `s[i−1] ≤ a && s[i] > a` within the last n sessions.
- `bandar`, `topacc` and `bavg` have no crossing or "within N" operator, so one as-of date per (D, top) is enough to evaluate them (corrected; HTML 830-835).
- `evalCond` collects event markers over the last 130 sessions for **every** evaluated ticker; only `drawChart` draws them, for the selected ticker (corrected; HTML 1060, 1066, 1614).
- Bandar thresholds: `BANDAR = {acc:4, big:10}` (781) is reset to acc 6 / big 10 (1082). The user can edit it (1621, 1628) and it is saved with a screen (1643). It is global.

| # | Prototype metric (line) | Prototype formula (from code) | Real source | Class | Formula and grain match | Label |
|---|---|---|---|---|---|---|
| 1 | `bandar` Bandar status (830-832; helpers 781-784). Params: days 10, top 3. Ops: acc ≥ 6, bigacc ≥ 10, dist ≤ −6, bigdist ≤ −10, gt, lt. | Each broker's D-session net sum, sorted. B = Σ positives among the first `top`; S = Σ negatives among the last `top`. Ratio = 100·(B + S) / Σ_D traded value. | F05 `net_value` per (ticker, broker), summed over investor types (and boards, per the board decision) over D sessions. Denominator: Σ_D buy value (F06 `foreign_buy_*` + `domestic_buy_*`, or F03 `total_buy_value`). | **Dynamic** or **Snapshot** (not stored) | Equivalent if computed from F05 per broker with the denominator on the same board. F03 `top3_buyer_*` is **not** equivalent: one day only, buyers only, denominator = positive net. The ranking rule is the same as Backtest `top5Accumulation` (flow.ts:108-119, top 5 fixed, no denominator). Formula and thresholds need approval: the Terminal's Bandar detector is hidden for the same reason (DESIGN.md:40, 147). | FACT |
| 2 | `topacc` Top-N broker net (833). Params: top 5, days 10, Rp B. | (B + S) / 1e9 of the same ranking | F05 | **Dynamic** or **Snapshot** | Equal to Backtest `top5` **only with top = 5 and all boards** (corrected). The Backtest also uses the price-bar calendar and starts at bar `from + n`. The prototype sends `topacc` to the Backtest as `top5` whatever its `top` (l.1669). | FACT |
| 3 | `broker` Broker net buy (834). Params: code (default YP), days 5. Ops: gt, lt, between, xa. | RSUM(net[broker], D) / 1e9 | F05 filtered on the broker, both investor types, over D sessions | **Dynamic** (cheap) | Equivalent to Backtest `broker` (all boards). F02 cannot be used at the latest date because it is sparse (B.3). Cost: D = 5, 31-34 ms; D = 20, 85-103 ms for one broker across all tickers (corrected; F05 has no (broker, trade_date) index). The broker list should be the 112 codes of `IDX_Broker_Profile`, not the 14 sample brokers. `xa` needs D + n sessions of daily nets. | FACT |
| 4 | `bavg` Price vs bandar average (835; 786). Param: days 10. Op: between −3..3. | Top-3 D-day net buyers; average = Σx⁺ / Σ(x⁺ / typical price) over their net-buy days (a net-weighted harmonic mean of the typical price); value = (close / average − 1)·100 | F05 `buy_value`, `buy_lots` of the top-3 D-day net buyers; close from price | **Dynamic** or **Snapshot** | **Not equivalent by formula.** The prototype approximates with the typical price because its sample has no broker prices. Real data gives the gross VWAP Σ`buy_value` / (Σ`buy_lots`·100), which equals Stockbit "Avg Buy" (verified, B.2) and the Terminal's `avgPrice` (brokerAgg.ts:25). | FACT; the choice of formula is PROPOSED / decision |
| 5 | `fnet` Foreign net flow (836). Param: days 5. Ops: gt, lt, between, xa, xb. | RSUM(foreign, D) / 1e9 | F06 `foreign_net_{1,5,10,20,40,60}d`, per board | **Precomputed feature** for D ∈ {1, 5, 10, 20, 40, 60}; **Dynamic** otherwise | Equivalent per board on ticker sessions. Other D: Σ `foreign_net_1d`, or a difference of `foreign_cumulative_net`. All boards: Σ `foreign_net_1d` over boards, **not** the sum of latest-date rows. xa / xb need the series over D + n sessions (multi-date read). | FACT |
| 6 | `fstreak` Foreign net-buy streak (837) | Consecutive sessions with foreign net > 0, ending today | F06 `foreign_net_1d` | **Dynamic** or **Snapshot** (not stored; `foreign_buy_days_Nd` are counts, not streaks) | Exact once the calendar is fixed. On market sessions a missed session breaks the streak. On 2026-10-27 the maximum streak is 21, and 27 tickers have ≥ 5, all universe stocks (verified). | FACT |
| 7 | `fpct` Foreign net % of value (838). Param: days 20. | 100·RSUM(foreign, D) / RSUM(val, D) | F06 `foreign_net_turnover_ratio_{1,5,20}d` = 100·ΣF / Σ(fb + db) | **Precomputed feature** for D ∈ {1, 5, 20}; **Dynamic** for others (from the 1d columns) | Equivalent by code. Recomputed = stored on 833 of 865 rows; all differences are tickers with fewer than 20 market sessions (ticker-session vs market-session windows) (verified). | FACT |
| 8 | `freq` Frequency spike (839). Param: len 20. Ops: gt, lt, xa (preset: xa 2.5 within 3). | trades[i] / SMA(trades, len)[i − 1] | F06 `foreign_buy_freq_1d + domestic_buy_freq_1d` = trade count | **Dynamic** or **Snapshot** (not stored) | Equivalent once trade count = buy-side frequency: buy freq = sell freq on every row checked (verified; reading the sum as "trades" is INFERENCE). The price table has no frequency, so this metric depends on broker data and its lag. Null for warrants. | FACT / INFERENCE |
| 9 | `silent` Silent accumulation (840-841). Params: days 5, len 20, volx 1.5 (preset 1.3), move 3 (preset 4). | SMA(v, days)[t] / SMA(v, len)[t − days] ≥ volx **and** \|c/c[t − days] − 1\|·100 ≤ move; needs t > days + len | Price close and volume (Regular-board volume) | **Dynamic** (price-based, no broker data) | Technical area. The preset combines it with `bandar` > 0. | FACT |
| 10 | `mfi` Money Flow Index (**842**, corrected from 841-843) | Prototype MFI (771) | Registry I47 `F.mfi`; equal to TA-Lib MFI | **Dynamic** via `F` (or a technical snapshot) | Prototype MFI equals `F` over the last 250 bars on 5 tickers. Edge rule: `q‖1e-9` (771). | FACT |
| 11 | `cmf` Chaikin Money Flow (**843**, corrected) | Prototype `CMF()` (772) with `((H − L)‖1)` | Registry I45 `F.cmf` | **Dynamic** via `F` | Equal to `F` over the last 250 bars on 5 tickers | FACT |
| 12 | `obv` On-Balance Volume (**844-845**, corrected). Param: len 20. Ops: rising [state], high [event]. | OBV starting at 0 (773); rising = OBV > SMA(OBV, len); high = OBV > max of the prior len bars | Registry I40 `F.obv` | **Dynamic** via `F` | Both operators ignore the constant offset. "Rising vs SMA" is start-independent, but floating ties on flat windows need a tie rule (BNBR: 358 of 358 disagreements on flat-OBV windows). | FACT |
| 13 | `adv` Average daily value (**846**, corrected from 844). Param: len 20. Also drives the universe `advMin` (default 1 B) and the "Avg value" column. | SMA(close × volume, len) / 1e9 | Price close × volume (Regular-board volume); or exact Regular value: F06 fb + db, or F03 `total_buy_value` | **Dynamic** (F03 20-day sums: 347 ms cold / 14 ms warm) or **Snapshot** | close × volume vs exact value (corrected): 1 day, 828 stocks: median 1.45%, p90 4.05%, p99 7.92%, max 14.8%. 20-session mean, 840 stocks: median 0.67%, p90 2.57%, max 15.3%. 2 stocks land on opposite sides of the 1 B threshold. The price-based version does not depend on the broker lag. Same definition as core `liquidity` (signals.ts:174). | FACT |

**Dead code (FACT).** `bandarStatus` (784) and `topBrokers` (785) are defined but never called.

**Bandarmology and combined flow presets (FACT, HTML 1084-1089, PRESETS).**

| Preset | Conditions | Data needed |
|---|---|---|
| Big Accumulation | bandar(10, 3) bigacc + close > MA20 | Broker ranking + price |
| Foreign Accumulation Streak | fstreak > 4 + fnet(20) > 0 | F06 (streak dynamic or snapshot; fnet20 stored) |
| Silent Accumulation | silent(5, 20, 1.3, 4) + bandar(10, 3) > 0 | Price + broker ranking |
| Frequency Spike | freq(20) crosses above 2.5 within 3 + ret(1) > 0 | F06 frequency for the last 24 sessions + price |
| Near Bandar Average Price | bavg(10) between −3 and 3 + bandar acc(10, 3) | Broker ranking + VWAP + close |
| Broker Follow | broker(YP, 5) > 1 B + close > MA50 | F05 one-broker query + price |
| Quality + Foreign Inflow (combined) | roe > 15, der < 1, fnet(20) > 0, close > MA50 (corrected) | F06 stored + price; fundamentals **unavailable** |
| Value + Accumulation (combined) | pb < 1.5, pe < 12, bandar acc(10, 3) | Broker ranking; fundamentals **unavailable** |

FACT (verifier): every flow preset uses a fixed grid: bandar(10, 3), bavg(10), broker(YP, 5), fnet(20), fstreak, freq(20), silent(5, 20, 1.3, 4).

---

### B.2 Live state of the flow tables

FACT: pgweb 2026-10-27 19:33 UTC, re-read by the verifier at 19:50 UTC (`audit/verify_flow.json` confirmed C1, "Section 1 table").

| Table | reltuples | Total size | Grain (PK) | Latest date | Earliest | Useful indexes | Heap correlation |
|---|---|---|---|---|---|---|---|
| `IDX_Broker_Summary` | 45.07 M | 10 GB | ("Date", "Symbol", "Broker", "Investor Type", "Market Board") | 2026-10-27 | 2016-01-04 | pkey only (date-leading) | — |
| `Feature_05_Foreign_Domestic_Broker_Detail` | 46.24 M | 9.8 GB | (ticker, trade_date, broker, investor_type, market_board) | 2026-10-27 | 2016-01-04 | pkey; `trade_date_idx` | trade_date 0.990 |
| `Feature_02_Broker_Rolling` | 46.29 M | 15 GB | (ticker, market_board, broker, investor_type, date) | 2026-10-27 | 2016-01-04 | pkey; `(date, market_board, ticker)` | — |
| `Feature_03_Stock_Broker_Daily` | 2.32 M | 1.09 GB | (ticker, market_board, date) | 2026-10-27 | 2016-01-04 | pkey; `(date, market_board, ticker)` | date 0.897 |
| `Feature_06_Foreign_Domestic` | 2.31 M | 1.37 GB | (ticker, market_board, trade_date) | 2026-10-27 | 2016-01-04 | pkey; `(trade_date, market_board)` | ticker 0.969, trade_date 0.047 |
| `IDX_Broker_Profile` | 112 | 80 kB | broker_code | — | — | pkey | — |
| `_INDEX` tables (IHSG) | F02/F05 585k; F03/F06 7.3k | small | as their parents | 2026-10-27 | — | — | — |
| `Feature_05/06_*_Stock` | views | — | parent filtered to `IDX_Stock_Universe` "Security Type" = 'stock' (DATABASE_SCHEMA.md 4264-4340) | — | — | — | — |

**Coverage on 2026-10-27 (FACT).**
- F05: 24,860 rows (Regular 24,503); recent dates hold 23.3k-26.7k rows each.
- F06 and F03: Regular 865, Nego 130, Tunai 9 rows.
- Price: 829 tickers = 828 universe stocks + IHSG. All 828 priced universe stocks have an F06 Regular row. The other 16 universe stocks did not trade.
- 37 F06 Regular tickers are outside `IDX_Stock_Universe`: ETFs and similar (X…), plus five 4-letter tickers, AKKU, CRAB, GTBO, TRUE and UNSP. A universe driven by `IDX_Stock_Universe` excludes them. Disclose this or confirm it with the user.

**History depth (FACT, approximate, F06 Regular, 844 universe stocks).**
- ≥ 60 sessions: 844; ≥ 252: 833; ≥ 312: 830.
- Median 1,931.5; p10 716; minimum 76.

**Data facts verified (FACT).**
- **Frequency.** Buy freq = sell freq on 865/865 latest Regular rows and on 18,546/18,546 rows of October 2026 (Regular 16,392, Nego 2,068, Tunai 86). 0 nulls in 161,294 universe Regular rows in 2026. Nulls exist only for warrants and rights. BBCA 81,369 and BBRI 60,879 trades on 2026-10-27.
- **Volume.** Price volume = Regular `buy_lots` × 100 on 10/10 tickers on 2026-10-27 and on 11/11 historical samples (2019-03-12, 2022-06-15, 2025-06-10). BBCA all boards 457.17 M vs price 366.85 M. INFERENCE: price-based volume metrics (volume spike, OBV, MFI, CMF, silent) are Regular-board metrics.
- **Average price.** `Avg Buy` / `Avg Sell` = value / (lots × 100) on 574 buy rows and the sell rows of 7 tickers; max difference 8.2e-13 / 9.0e-13.
- **Broker profile.** 112 brokers: Institutional-heavy 25, Mixed 23, Niche 45, Retail-heavy 19. YP, ZP, YU, DR and KK are `broker_type` Foreign and Retail-heavy. All 89 brokers trading on 2026-10-27 are in the profile. The classification is current-state, not point-in-time.
- **Feature_Catalog.** Active rows: F02 v2 (38), F03 v2 (24), F05 v1 (15), F06 v1 (87), all `CALCULATION_VERIFIED`. F03 `institutional_net_value` has `point_in_time_safe = false`.
  - F06 misuse warning: "Do not compare across boards or sum across boards."
  - F03 warning: "Do not combine Regular, Nego and Tunai implicitly."
- **Source gaps (M157).** The flow audit found 4 `source_balance_gap` rows since 2025, all structured warrants. Whether that count holds is UNKNOWN: the verifier's bounded re-check hit the 30 s timeout (check: a re-run bounded to one year per statement). Low impact (INFERENCE).
- **Live functions.** The `refresh_feature_02` body equals migration `20261025_008`. The `refresh_feature_06` body equals `20261022_005:66-298`; `20261022_003` is identical after renames (diff 0 of 233 lines).

---

### B.3 Definitions that decide equivalence (FACT, from code)

- **F05** (`20261022_002:63-95`, identical in `20261022_005`): one row per `IDX_Broker_Summary` row. No window. Net = buy − sell. Carries `buy_freq` and `sell_freq`.
- **F06** (`20261022_003:145-382`):
  - Grain (ticker, board, date). A row exists only where the board traded that day (`WHERE x.active`).
  - Windows count **ticker sessions**: dates on which the ticker has any F05 row on any board. Every board is zero-filled inside the window.
  - `foreign_net_turnover_ratio_Nd` = 100·ΣF / Σ(fb + db).
  - z-score and percentile windows use the 252 or 60 **preceding** rows; today is excluded.
  - Stored windows: net 1/5/10/20/40/60; ratio 1/5/20; buy and sell days 5/10/20/40 (no 60-day days column).
  - **Consequence:** an all-board N-day value cannot be read by summing the latest-date rows. All-board values must be summed from `foreign_net_1d`.
- **F02** (`20261025_008:52-193`):
  - Grain (ticker, board, broker, investor_type, date). Rows are written only where that combination traded that day (`FROM history JOIN daily`).
  - **Consequence:** on the latest date F02 is sparse. Over 2026-09-30..10-27:
    - ANTM foreign 20-day net from latest-date rows: Regular −408.39 B + Nego 0.34 B = −408.05 B, against a true −477.11 B;
    - DMAS 39.09 B vs 82.41 B;
    - combinations with a latest-date row: ANTM 79/143 (88.6 B of |net20| missing), BBCA 112/169 (658.6 B), DMAS 52/94 (61.5 B).
- **F03** (`20260914_047:30-129`):
  - Daily only, per (ticker, board); brokers are first summed over both investor types.
  - Stores top buyer and seller, top-3 buyer net and share, HHI, net-buy and net-sell broker counts and ratio, foreign and domestic net, and institutional / retail / mixed / niche net. The four classes sum to the total net (ANTM 2026-10-26: −76.54 + 40.34 + 32.72 + 3.48 = 0).
  - `top3_buyer_share` = top-3 positive daily net / `positive_net_value_total`, one day only (`20260914_047:105-123`).
  - `net_buy_broker_ratio` = `net_buy_broker_count / active_broker_count`. On 79 of 865 rows `active_broker_count` ≠ buyers + sellers, because brokers with zero net are counted (corrected).
- **"Foreign"** means the source **investor type**, not broker domicile, everywhere (publisher `broker_doc`, `apps/terminal-publisher/publisher.py:165-172`). The prototype's `BROKERS` list (HTML **667**, corrected from "572ff") carries a domicile flag and marks YP (Mirae) domestic, while `IDX_Broker_Profile` has YP as Foreign. The prototype's foreign series is generated separately (l.700), so there is nothing to match.
- **Backtest and Terminal flow** (`apps/edge-bff/backtest/src/core/flow.ts:1-121`):
  - calendar = the ticker's price bars;
  - `fnet` = foreign investor-type net over **all boards**;
  - `broker X` = both investor types, all boards;
  - `top5Accumulation` takes, on each bar, the positives among the first 5 plus the negatives among the last 5 of the n-bar broker sums, starting at `from + n`.
- **No ranking columns (FACT).** No stored column holds a D-day broker ranking, top-N net, bandar VWAP, streak or D-day breadth in F02, F03, F05 or F06 (`evidence/verify_flow/f06_cols.txt`).

---

### B.4 Board differences

| Fact | Evidence | Label |
|---|---|---|
| Price volume is Regular-board volume | B.2 | FACT |
| Regular vs all-board 20-day foreign net: **168 of 841** universe stocks differ (corrected from "of 844"; 841 = stocks with any F06 row in 2026-09-30..10-27). 59 differ by > 10%; 20 flip sign. CARE: −1.50 B Regular vs +376.22 B all boards. | `evidence/verify_flow/c11.sql`; `audit/verify_flow.json` C11 | FACT |
| The F06 catalog warns against summing or comparing across boards. The Backtest (`fnet`, `broker`, `top5`) and the Terminal use all boards. | Feature_Catalog; flow.ts:8-14 | FACT |
| The Terminal's shipped "Top accumulators" ranks by Σ net value, all investors, **all boards**, 5 sessions by default. A Regular-board screen can show different top brokers for the same stock. Since P8 (b) only the labelled Regular variant does. | DESIGN.md:38; `audit/verify_flow.json` additional findings | FACT |
| Send to Backtest: from a Regular-board screen, the sent `fnet` / `broker` / `top5` conditions are evaluated on all boards in the Backtest. Nothing breaks (the types exist, `backtest/src/core/catalog.ts:53-55`), but the values differ. Since P8 (b) this applies only to the Regular variant, which is listed as left out. | `audit/verify_flow.json` additional findings | FACT |
| Whether Stockbit's or IDX's public "foreign net" uses the Regular board or all boards | No external call was made | UNKNOWN |
| Board choice for the screener: Regular by default, with an all-board toggle computed from the 1d columns (the flow audit's proposal). Superseded: the user chose all boards as the default on 2026-10-28 (P8 b), with a labelled Regular variant | `audit/flow.md` 0.6(a); UNKNOWNS / PRODUCT DECISIONS P8 | PROPOSED (audit) / DECIDED (P8 b) |

---

### B.5 Broker lag (M243) and how a round starts

**Now (FACT, re-read 19:50 UTC).**
- The latest final Daily price is 2026-10-27. `IDX_Broker_Summary`, F05, F02, F03 and F06 also end on 2026-10-27, so the lag is **0 sessions**.
- The lag was closed by stockbit-updater round `38cdc7dc` (APPLY 11:08-12:58 UTC): 48,661 broker rows for 2026-10-26/27; features 2,214.2 s; INDEX 2,077.2 s.
- Earlier the same day (08:19 UTC) broker data ended on 2026-10-23 while price was on 2026-10-26.

**How a round starts (corrected; the flow audit's C2 was refuted).**
- FACT: **one round runs per deployment of stockbit-updater**, including the redeploy Railway starts after a variable change.
- FACT: replacing `STOCKBIT_TOKEN` is the documented way to start one. There is no schedule, and a push to `main` never starts a round.
- FACT: on 2026-10-27 three rounds ran between 14:18 and 14:53 UTC with an unchanged `token_expires_at` of 2026-10-28 10:53 UTC. After that time every round fails until a new token is set.
- INFERENCE: the broker lag recurs unless someone deploys with a valid token after each session. The screener therefore needs a broker as-of date shown separately from the price date.
- Evidence: `apps/stockbit-updater/README.md:8, 20-21`; `UPDATE_TABLE.md:14`; `Monitoring_Stockbit_Update` rows `3323340d`, `e3331473`, `51a399f1`.

**Monitoring gate trap (FACT, verifier).**
- `Monitoring_Stockbit_Update` has a stale RUNNING row `e3331473` (started 14:25:02 UTC, `updated_at` 14:25:08, no `finished_at`). It was superseded by `51a399f1` (SUCCESS 14:28-14:53, 0 broker rows).
- The round before it, `3323340d`, FAILED (14:18-14:24) with `TypeError: Object of type date is not JSON serializable`.
- A gate on "no RUNNING row" would block forever. Gate instead on the newest row by `started_at` being SUCCESS, or on the publisher `state.json` `broker_through` / `broker_behind_sessions` (ERRORS M243).
- At the audit a grep found neither the stale row nor that error in `ERRORS_AND_SOLUTIONS.md` or `RAILWAY_CHANGELOG.md`. Both were recorded on 2026-10-28: ERRORS D24 (the FAILED round, root cause suspected) and D25 (the RUNNING row left open).

**Cross-table skew during a round (FACT, `apps/stockbit-updater/refresh.py`).**
- F05 is written and committed per date for all tickers at once (102-111).
- F02 follows per ticker (118-121), then F03 per date after all of F02 (129-130), then F06 per ticker (138-139).
- `run_in` opens a connection and commits per call (68-74).
- For most of the about 37 minutes of features, F05 already holds the new date for every ticker, while F03 lacks it and F06 is partial.
- INFERENCE: a screener or snapshot that combines F05 rankings with F06 or F03 must read only after the round reaches SUCCESS.

**Pipeline risk of an inline snapshot step (INFERENCE, `updater.py:134-162`).**
- The broker load, features, INDEX, events and table status run in one `try` block.
- A snapshot step placed inline in `refresh_broker_features`, or after it, would on failure mark the round FAILED and skip INDEX, events and `Database_Table_Status`.
- It would need its own `try`, or must run after table status. A publisher-written file does not have this coupling.

---

### B.6 Session calendar

| Fact | Label |
|---|---|
| Stored F06 and F02 windows count ticker sessions | FACT |
| The flow audit's dynamic queries (Q2b) and proposed snapshot use market sessions | FACT / PROPOSED |
| They differ only for tickers with missing sessions: 18 of 865 at 20 days | FACT |
| No stock has a price row on 2026-09-17 or 2026-09-18, which are real sessions with broker data (ERRORS M238, OPEN). A price-bar calendar (Backtest `flow.ts`) and a broker-session calendar therefore disagree across that span. | FACT (`audit/verify_feature04.json` F04-06) |
| Pick one calendar and disclose it (M209 lesson) | PROPOSED |

---

### B.7 Flow metric set proposed by the flow audit (audit input; labelled PROPOSED)

**Defaults the audit proposes.**
- Regular board, with an all-board toggle where noted.
- Investor type = source investor identity.
- Broker net = both investor types summed.
- Windows in sessions: market sessions for dynamic and snapshot metrics; stored F06 windows stay on ticker sessions.

Thresholds are not validated. Costs are measured single runs; see PERFORMANCE EVIDENCE 11.7 for the re-run variance.

**Cost codes.**

| Code | Meaning | Measured cost |
|---|---|---|
| S | Read the stored F06 / F03 latest cross-section | 22.6 ms (Q1) |
| W | Short window over F06 / F03 | 14 ms-1.5 s recorded; multi-date F06 windows re-ran at 3.3-7.3 s with one > 30 s timeout |
| B | F05 broker-ranking aggregate | 0.5-12 s recorded; re-runs 4.1-4.9 s |
| Snap | One row per (date, ticker) from a snapshot | INFERENCE: milliseconds |

| ID | Metric | Formula | Source columns | Grain | Unit | Params | Cost now → with snapshot | Corrections and caveats |
|---|---|---|---|---|---|---|---|---|
| F1 | Foreign net N | Σ_N F | F06 `foreign_net_{1,5,10,20,40,60}d`; all boards: Σ F06 `foreign_net_1d` | ticker × board × date | IDR (Rp B) | N ∈ {1, 5, 10, 20, 40, 60} | S (Regular) / W (all boards) | — |
| F2 | Foreign net % of traded value N | 100·Σ_N F / Σ_N (fb + db) | F06 `foreign_net_turnover_ratio_{1,5,20}d`; 10 and 60 from the 1d columns | same | % | N ∈ {1, 5, 10, 20, 60} | S / W | — |
| F3 | Foreign net-buy day ratio N | `foreign_buy_days_Nd` / N | F06 `foreign_buy_days_{5,10,20,40}d` | same | 0-1 | N ∈ {5, 10, 20, 40} | S | — |
| F4 | Foreign streak (signed) | +k consecutive F > 0 sessions, −k consecutive F < 0, ending at the as-of date | F06 `foreign_net_1d` | ticker × date | sessions | capped at 60 | W → Snap (incremental from yesterday) | — |
| F5 | Unusual foreign flow | z-score and own-history percentile of the N-day net | F06 `foreign_net_zscore_*_base252d`, `_percentile_*` (and base60d) | ticker × board × date | σ / percentile | N + history | S | **Corrected:** NULL until the ticker has 252 non-null prior N-day values, i.e. ≥ 252 + N ticker sessions (271+ for N = 20). Today 11 universe stocks have fewer than 252 F06 Regular rows (min 76) and 14 fewer than 312. The prototype counts n/a as a fail (HTML 1063), so disclose it. |
| F6 | Foreign flow acceleration | F_20 − F_prev20 | F06 `foreign_flow_vs_prev_20d` / `_40d` | same | IDR | 40 / 80 sessions | S | — |
| F7 | Foreign strength | 100·ΣR / Σ\|R\|, R = F/T | F06 `foreign_strength_20d` / `_50d`, `_momentum_5d` | same | −100..100 | 20 / 50 | S | EDGE formula; no thresholds defined |
| F8 | Cross-sectional foreign rank | Percentile of F2 across the screened universe | Computed at query time from F2 | universe × date | 0-100 | — | trivial (about 850 values) | Population is a decision |
| B1 | Top-N broker net D | Σ positives of the top-N D-day broker nets + Σ negatives of the bottom N | F05 `net_value` per (ticker, broker) over D | ticker × date | IDR | N ∈ {3, 5}, D ∈ {5, 10, 20} | B (whole grid for one date: 1.47 s / 4.73 s recorded; 4.09 s re-run) → Snap | With N = 5 and all boards it equals Backtest `top5` |
| B2 | Bandar ratio D (Acc / Big Acc / Dist / Big Dist) | 100·B1 / Σ_D buy value | F05 + F06 (fb + db) | ticker × date | % | thresholds editable (prototype 6 / 10) | B → Snap | **Formula approval needed** (DESIGN.md:40) |
| B3 | Close vs top-3 buyer VWAP D | 100·(close / VWAP − 1), VWAP = Σ`buy_value` / (Σ`buy_lots`·100) of the top-3 D-day net buyers | F05 `buy_value`, `buy_lots`; price close | ticker × date | % | D ∈ {10, 20} | B → Snap | Not equal to the prototype's `bavg` (B.1 row 4) |
| B4 | Broker net D (chosen broker) | Σ_D net of broker X, both investor types | F05 filtered on the broker | ticker × date | IDR | any broker, D ≤ 20 | **Corrected:** dynamic, 31-34 ms at D = 5 and 85-103 ms at D = 20 (F05 has no (broker, trade_date) index); no snapshot needed | — |
| B5 | D-day broker breadth | net buyers / (net buyers + net sellers) on D-day broker nets | F05 | ticker × date | 0-1 | D ∈ {5, 20} | B → Snap | **Corrected:** F03 `net_buy_broker_ratio` is **not** the 1-day equivalent; its denominator counts active brokers with zero net (79 of 865 rows differ). Use buyers / (buyers + sellers) from F05 or the snapshot, or define B5 as F03's ratio. |
| B6 | Buying concentration D | top-3 D-day buyers' net / Σ positive D-day net | F05 (1 day: F03 `top3_buyer_share`) | ticker × date | 0-1 | D ∈ {1, 20} | S (1 day) / B → Snap | — |
| B7 | Net-flow HHI (1 day) | Σ(\|net\| / Σ\|net\|)² | F03 `broker_concentration_hhi` | ticker × board × date | 0-1 | 1 | S | — |
| B8 | Top buyer / top seller D (display) | argmax / argmin of the D-day net | F05; 1 day: F03 `top_buyer` / `top_seller` | ticker × date | code | D ∈ {1, 20} | S / Snap | — |
| C1 | Institutional vs retail net D | Σ_D `institutional_net_value`, Σ_D `retail_net_value`, each as % of Σ_D `total_buy_value`; divergence = inst% − retail% | F03 | ticker × board × date | IDR, % | D ∈ {5, 20} | W (14 ms warm / 347 ms cold) | **Corrected caveat (INFERENCE):** F03 joins `IDX_Broker_Profile` when each row is refreshed, and only changed dates are refreshed. A row carries the classification of its last refresh: current for new rows, possibly stale for old ones. The catalog marks it `point_in_time_safe = false`. "Foreign broker" ≠ "foreign investor" ≠ "institution". |
| D1 | Trades and frequency spike | trades = fbf + dbf; spike = trades_t / mean(prior 20) | F06 frequency columns | ticker × date | count, × | 20 | W → Snap | Depends on broker data and its lag |
| D2 | Ticket-size change | (value / trades)_5 vs prior 20 | F06 `*_value_per_freq_change_5d_vs_prev20d` (by investor type), or derived | ticker × board × date | % | 25 | S / W | — |
| D3 | ADV N (exact) | mean_N (fb + db) | F06, or F03 `total_buy_value` | ticker × date | IDR | N ∈ {5, 20, 60} | W → Snap | PROPOSED: the universe ADV filter uses price (close × volume), so it does not go stale with the broker lag |
| D4 | Foreign participation | (`foreign_buy_share` + `foreign_sell_share`) / 2 | F06 `foreign_buy_share_1d`, `foreign_sell_share_1d` | same | % | 1 (snapshot 20) | S | — |

**New Bandarmology presets the flow audit proposes (PROPOSED; thresholds not validated).**
- "Foreign accumulation, unusual": F2(20) > 3% and F5 z20 ≥ 2.
- "Quiet bandar": B2(10) ≥ 6 and B6(20) ≥ 0.6 and |ret 10| ≤ 4%.
- "Retail out, institutions in": C1 inst% > 0 > retail% over 20 sessions.
- "Accumulation near cost": B3(10) within ±3% and B2(10) ≥ 6.
- "Breadth turn": B5(5) − B5(20) ≥ 0.15.

---

### B.8 Is a daily flow snapshot needed? (audit input)

| Statement | Label |
|---|---|
| Fixed-window F06 metrics (F1-F3, F5-F7, D4) need no snapshot. The latest F06 cross-section reads in milliseconds (Q1: 176 heap blocks). | FACT (measured) / PROPOSED |
| Broker-ranking (B1, B2, B3, B5, B6), streak (F4) and frequency-spike (D1) metrics are not stored. Whole-universe multi-date aggregates take **about 3-8 s, with occasional timeouts** over 30 s, on this 128 MB-buffer database shared with the AI workload. Each run spills to disk at `work_mem` 4 MB. | FACT (verifier re-runs) |
| A daily snapshot, grain (as-of date, ticker), Regular board, fixed parameter grid, is recommended for those metrics | INFERENCE / PROPOSED (flow audit C14) |
| **Uncertain rationale (verifier).** The flow audit said the dynamic cost "multiplies with 'within N days' operators". That does not apply to the ranking metrics, which have no crossing operator in the prototype. Better drivers: (1) the prototype's `libCounts` evaluates every preset and saved screen over the whole universe at boot, after a threshold edit and after save, delete or duplicate; (2) every flow preset uses a fixed grid, so a fixed-grid snapshot or precomputed preset counts cover all of them; (3) the cold-cache variance. | FACT (code) / INFERENCE |
| Snapshot refresh cost: about 1.5-5 s per new date for the F05 grid plus about 1 s for F06; about 140-400 KB per date (35-100 MB a year); a 252-day backfill about 6-20 min one-off | INFERENCE (arithmetic on single-run timings; the re-run variance points to the upper end) |
| Vehicles, all needing the user's "go": (a) a new governed table (e.g. `Feature_07_Flow_Screener`) refreshed by stockbit-updater after F06 and F03, needing a migration, catalog rows, `measure_indexes.py` and onboarding, and carrying the pipeline risk of B.5; (b) a publisher-written daily file with the last W + 1 dates, published when `broker_behind_sessions` = 0 (no schema change); (c) on-demand compute with an in-process cache keyed by the broker as-of date (the first request after a refresh pays the cold cost) | PROPOSED |
| Custom parameters: a snapshot serves only its grid (D 5/10/20, N 3/5). Either restrict the UI to the grid, or allow custom D ≤ 20 on demand, with a cap and caching. | PROPOSED |
| Whole-universe screening from the published per-ticker broker files is impractical: the 12 largest files hold 28.4 MB gzip; BBRI alone is 2.2 MB gzip / 14.5 MB inflated; F05 holds 46.2 M rows, above `BACKTEST_MAX_BROKER_ROWS` (20 M) | FACT (documents) / INFERENCE (conclusion) |
| Every proposal here is additive. The Backtest flow conditions read published per-ticker broker files built from F05 (`publisher.py` `BROKER_SQL`; conditions.ts:190-245), so a new table, file or endpoint does not touch them. | FACT (data path) / INFERENCE |
| Queries must pass literal date bounds: a CTE-joined calendar without one produced an 18.6 s sequential scan (Q2) | FACT |

---

### B.9 Open flow decisions surfaced by the audit

Where each is settled (UNKNOWNS / PRODUCT DECISIONS): 1 → P8, DECIDED 2026-10-28 (all boards); 2 and 3 → P9; 4 and 5 → the design (TARGET ARCHITECTURE §6.11: publisher window files, custom windows within the published window, P5); 6 → P10; 7 → P20 (b); 8 → ADV = close × volume over 20 bars, the Backtest's `liquidity()` (TARGET ARCHITECTURE §6.12); 9 → P20 (a); 10 → P20 (c), with the orphans recorded as ERRORS D29; 11 → U9. P9, P10 and P20 are decided after FLOW INDICATOR PROPOSALS (PHASE 2).

1. **Board.** Regular only (consistent with price volume) or all boards (the Backtest and Terminal default)? 168 of 841 stocks differ on the 20-day foreign net; 20 flip sign.
2. **Bandar.** Approve a formula, window, top-N, denominator and thresholds (prototype: ratio, acc 6% / big 10%, top 3, 10 sessions)? The Terminal's Bandar detector waits for the same approval. Should thresholds stay user-editable, global and saved per screen?
3. **Price vs bandar average.** The gross VWAP of the top-3 D-day net buyers (equal to Stockbit Avg Buy), or the prototype's net-weighted typical price?
4. **Grid.** A fixed parameter grid served from a snapshot, or custom D computed on demand with a cap (for example D ≤ 20)?
5. **Snapshot vehicle.** (a) a governed table, (b) a publisher file, or (c) an in-process cache?
6. **Broker lag.** When broker data lags price: evaluate flow conditions at the broker as-of date with a label, exclude them, or block combined screens?
7. **Calendar.** Market sessions or ticker sessions for dynamic and snapshot windows?
8. **ADV.** Price close × volume (no broker lag, about 0.7% median off over 20 sessions) or the exact broker traded value?
9. **Default broker.** YP (prototype Broker Follow) or YU (Backtest default, `backtest/src/core/catalog.ts:54`)?
10. **Non-universe tickers.** Include or exclude the 5 tickers with flow rows but no universe or price row (AKKU, CRAB, GTBO, TRUE, UNSP)?
11. **"Existing screener".** Which one the user means (B, user context).


## APPENDIX C — FUNDAMENTALS AND UNIVERSE DATA

**Sources.**
- Audits: `audit/fundamentals_universe.md` (read-only, repository `3db84ae`, live pgweb 2026-10-27) and `audit/html_model.md` sections 1-2.
- Raw evidence: `evidence/fundamentals_universe/`. Evidence notation as in the header: `audit/<area>.md` and `audit/verify_<area>.json` (reports and verifications), `evidence/<area>/<file>` (raw outputs), all relative to `verification/screener/`; repository `path:line` citations are at `main` `010af1e`.
- No adversarial verifier re-ran this area. Its figures stand as the auditor measured them, with the cross-checks named below.
- Prototype lines refer to the user's upload `screener EDGE layout.html` (1,717 lines, not committed).

**Labels.**
- FACT: seen in code, data or a measurement.
- INFERENCE: concluded from facts.
- PROPOSED: a recommendation.
- UNKNOWN: not established.

---

### C.1 Headline

| # | Statement | Label | Evidence |
|---|---|---|---|
| 1 | No source of financial-statement fundamentals exists anywhere in the system: no table, no loader, no endpoint, no catalog row. The external-provider registry of `market-sql-governor` is empty. | FACT | `evidence/fundamentals_universe/column_search.txt`; `apps/market-sql-governor/app/external.py:1-12, 56, 106-108` |
| 2 | Of the prototype's 32 Fundamental metrics, **0 are available now**. **2 are derivable** from existing data with caveats (dividend yield, years of dividends). **25 universal metrics need new data**; market cap among them has a plan (EXEC-MCAP) that waits for "go". **5 are bank-only** (NIM, NPL, CAR, CASA, LDR); they need new data and do not apply to non-banks. | FACT | C.3 |
| 3 | None of the 8 Fundamental presets can run today. "High Dividend" is 2 of 3 derivable. The 3 Combined presets can run only their technical or flow halves. | FACT | C.5 |
| 4 | Universe: sector, industry, price and ADV can be served now from live data. Index membership, listing board, free float, special notation / FCA and listing date have no source. Market cap waits for EXEC-MCAP. | FACT | C.6, C.7 |
| 5 | `Universe_Equity_Description` has Sector and Industry swapped relative to `IDX_Stock_Universe`: 841 of 844 rows differ; the other 3 compare equal only because both columns hold `Undefined` (per the audit). ERRORS D23 now records it (OPEN, commit `641e55e`). The screener must read classification from `IDX_Stock_Universe` only. | FACT | `evidence/fundamentals_universe/ued.txt`; ERRORS_AND_SOLUTIONS.md D23 |

---

### C.2 Where a fundamental source could be (search results)

| # | Place checked | Result | Label |
|---|---|---|---|
| 1 | Market DB tables and columns: 87 public relations | A column search for board, listing, notation, suspension, LQ45, IDX30, IDX80, ISSI, shares, outstanding, market cap, float, EPS, earnings, revenue, equity, dividend, book, fiscal period or report finds only `market_board` (the trading board) and `shares_*` in the insider and event tables. No statement, ratio, market-cap, shares-outstanding, free-float or index-membership column exists. | FACT (`evidence/fundamentals_universe/column_search.txt`) |
| 2 | `AI_metric_catalog` | 6 metrics, all price or flow | FACT |
| 3 | `AI_formula_reference` | 246 formulas. 4 need inputs the DB lacks: `CALC_066` Turnover Ratio (`shares_outstanding`), `CALC_067` Free Float Turnover (`free_float_shares`), `CALC_082` Sector Cap Weighted Return (`lagged_market_cap`), `CALC_059` (generic equity series). | FACT |
| 4 | `Feature_Catalog`, `AI_table_catalog`, `Table_Catalog` | 0 rows mention fundamentals, market cap or shares outstanding; no table has `data_domain` FUNDAMENTAL | FACT |
| 5 | `apps/stockbit-*` | The Stockbit endpoints in code are broker, activity, market detector, corporate action and major holder. No keystats or financial-statement endpoint is used. | FACT (`stockbit_ihsg_daily.py:162, 194`; `broker_import.py:129`; `stockbit_events.py:5-6`) |
| 6 | `apps/market-ai-orc/app/orchestrator.py:1279` | `OUTSIDE_DATA_RULE` tells the model that fundamentals are outside the catalog | FACT |
| 7 | EXEC.md EXEC-MCAP (8152-8270, "menunggu go") | **Part A:** daily market cap from the TradingView quote session (fields such as `market_cap_calc`, `total_shares_outstanding`, `float_shares_outstanding`); covers 820 of 844 stocks; no history (ingest starts on day 1). **Part B:** historical market cap from quarterly or yearly share counts, 779 stocks. Licence risk noted (8190-8193). Planned columns: `market_cap`, `shares_outstanding`, `market_cap_source`. Free float is **not** in the plan (8207-8211). | FACT |
| 8 | TradingView scanner | `apps/terminal-publisher/publisher.py:102, 132` POSTs to the scanner with columns `['name', 'logoid']` only. Whether it exposes IDX fundamentals, and under what licence, is unchecked. | FACT (use) / UNKNOWN (fundamentals) |
| 9 | `Postgres-E8GM` | Web-governor store only (`web_event_item`, `web_ask`, `web_fact`, …) | FACT (PROJECT_CONTEXT.md:14) |
| 10 | `DB2` | Captured in Railway config on 2026-09-13 (RAILWAY_CHANGELOG.md:3664); not declared in today's `.railway/railway.ts` (7-9); contents undocumented | FACT (absence) / UNKNOWN (content) |
| 11 | PLAN.md:321 | A user plan of 2026-10-09 ("bukan perintah jalan") to ingest "macro, fundamental, fx, cross market…" later; no source chosen | FACT |
| 12 | Onboarding rules | NEW_TABLE_ONBOARDING_PLAN.md:89, 129 and ERRORS Part A A2.7: fundamental onboarding must settle period type, fiscal period end vs filing date, restatements as versions, currency and scale, consolidated or parent, TTM and ratios as Features, and `release_date` with as-of joins | FACT |
| 13 | The xlsx spec (11 sheets) | Never mentions fundamentals, universe, sector, board or liquidity | FACT (`evidence/fundamentals_universe/scripts/xlsx_grep.py`) |
| 14 | Stockbit keystats API, IDX XBRL statements, OJK bank reports, KSEI ownership | Nothing in the repository references them | UNKNOWN |

---

### C.3 The 32 fundamental metrics

**How the prototype treats them (FACT).**
- `makeFundamentals` (713-733) builds a random snapshot per ticker; line 566 calls the financials "deterministic samples, not market data".
- Every metric is "Latest reported" (848), has no series, and is evaluated only on the last bar through `I.last` (1062). Only gt / lt / between apply.
- Banks (`industry === 'Banks'`) get `der`, `roic`, `evEbitda` and `intCov` set to null, plus five bank-only metrics. Financials get `grossMargin`, `curr` and `altman` set to null.
- Send to Backtest marks fundamental conditions "Screen only — it chose the tickers" (1684).

**Column meanings.**
- **Availability:**
  - **Available**: in the DB now.
  - **Derivable**: computable from existing data, with caveats.
  - **New data**: a new source is needed (**planned** = an approved plan waiting for "go").
  - **Bank-only**: applies to banks only; new data is needed.
- **Banks:** whether the metric applies to the 48 banks (`Industry = 'Banks'`; 100 stocks in `Sector = 'Financials'`).
- **Point-in-time requirement:** what a correct "today" value needs. A historical screen needs it as of each past date (C.4).

| # | Key | Label | Inputs a real version needs | Availability | Point-in-time requirement | Banks |
|---|---|---|---|---|---|---|
| 1 | `cap` | Market cap (IDR T) | close × shares outstanding, same split basis | **New data (planned, EXEC-MCAP A/B)** + decision (buckets) | Shares as of D on the same split basis as the price; Part B gives quarterly shares that can lag up to a quarter | yes |
| 2 | `pe` | P/E | price, EPS (TTM or FY), shares | New data + decision (TTM / FY; a loss gives n/m) | EPS from reports **published** by D; TTM built from de-cumulated quarters | yes |
| 3 | `pb` | P/B | price, equity attributable to the parent, shares | New data | Equity from the latest **published** report; shares on the same basis | yes |
| 4 | `peg` | PEG (P/E ÷ 3-year EPS CAGR) | P/E + 4 fiscal years of EPS | New data + decision | 4 FY reports, each as published by D; restatements kept as vintages | yes |
| 5 | `evEbitda` | EV/EBITDA | market cap, debt, cash, minorities, EBITDA | New data (+ planned market cap) | Balance sheet and TTM EBITDA as published by D; cap as of D | not meaningful (prototype null) |
| 6 | `divYield` | Dividend yield | trailing 12-month cash dividends per share ÷ close | **Derivable** + decision | Dividends usable from `ex_date` (announcement availability would need the payload field `dividend_created`, INFERENCE). Amounts and price must be on the same split basis. | yes |
| 7 | `payout` | Payout ratio | dividends ÷ net income | New data (net income) | Net income as published by D | yes |
| 8 | `divYears` | Years of dividends | years with a cash dividend | **Derivable** + decision (consecutive or total) | Ex-dates before D | yes |
| 9 | `roe` | ROE | net income, average equity | New data | Two balance sheets + TTM income, as published by D | yes |
| 10 | `roa` | ROA | net income, average assets | New data | Same | yes |
| 11 | `roic` | ROIC | NOPAT, invested capital | New data | Same | no (prototype null) |
| 12 | `netMargin` | Net margin | net income ÷ revenue | New data + decision (bank "revenue") | TTM, as published by D | definition differs for banks |
| 13 | `grossMargin` | Gross margin | gross profit ÷ revenue | New data | Same | no for Financials (prototype null) |
| 14 | `revG` | Revenue growth YoY | 2 periods of revenue | New data | Both periods as published by D | definition differs for banks |
| 15 | `epsG` | EPS growth YoY | 2 periods of EPS | New data | Same | yes |
| 16 | `epsGq` | EPS growth, latest quarter YoY | quarterly EPS. IDX interim reports are cumulative (Q1 / H1 / 9M), so quarters must be de-cumulated (INFERENCE). | New data + decision | Quarter as published by D | yes |
| 17 | `epsG3y` | EPS CAGR 3 years | 4 fiscal years of EPS | New data | 4 FY reports as published by D | yes |
| 18 | `der` | Debt / equity | interest-bearing debt or total liabilities, ÷ equity | New data + decision (definition) | Latest balance sheet as published by D | no (prototype null). INFERENCE: presets using `der` silently exclude banks. |
| 19 | `curr` | Current ratio | current assets ÷ current liabilities | New data | Same | no for Financials (prototype null) |
| 20 | `intCov` | Interest coverage | EBIT ÷ interest expense | New data | TTM as published by D | no (prototype null) |
| 21 | `fcfYield` | FCF yield | (CFO − capex) ÷ market cap | New data (+ planned market cap) | TTM cash flow as published by D; cap as of D | INFERENCE: not meaningful for banks; the prototype computes it for them |
| 22 | `piotroski` | Piotroski F-score | 2 fiscal years: NI, CFO, assets, long-term debt, current assets and liabilities, shares, gross margin, revenue | New data + decision | 2 FY reports as published by D | 2 tests undefined for banks; the prototype scores banks anyway |
| 23 | `altman` | Altman Z | working capital, retained earnings, EBIT, market value of equity, sales, assets, liabilities | New data (+ planned market cap) | Statements as published by D; cap as of D | no for Financials (prototype null) |
| 24 | `grahamRatio` | Price ÷ Graham number | √(P/E × P/B ÷ 22.5) | New data | As P/E and P/B | yes |
| 25 | `magicRank` | Magic Formula rank | cross-sectional ranks of earnings yield and ROIC | New data (+ planned market cap) + decision | All inputs as of D; the ranked population as of D | Financials excluded |
| 26 | `freeFloat` | Free float % | float shares ÷ shares | New data + decision | Float as of D. The TradingView field `float_shares_outstanding` exists (EXEC.md:8167-8169) but is not in the EXEC-MCAP plan. | yes |
| 27 | `foreignOwn` | Foreign ownership % | ownership by investor type (a registry such as KSEI, INFERENCE). Broker foreign **flow** is not ownership. | New data | Holdings as of D | yes |
| 28 | `nim` | NIM (banks) | bank income statement and earning assets | **Bank-only**, new data | Bank report as published by D | 48 banks only |
| 29 | `npl` | Gross NPL (banks) | loan-quality disclosure | **Bank-only**, new data + decision (gross or net) | Same | 48 banks only |
| 30 | `car` | CAR (banks) | capital-adequacy disclosure (not a standard statement line) | **Bank-only**, new data | Same | 48 banks only |
| 31 | `casa` | CASA (banks) | deposit breakdown | **Bank-only**, new data | Same | 48 banks only |
| 32 | `ldr` | LDR (banks) | loans ÷ deposits; the regulator's variant may differ (INFERENCE) | **Bank-only**, new data + decision | Same | 48 banks only |

**Totals (FACT).** Available 0; derivable 2; new data for universal metrics 25 (1 of them planned); bank-only 5.

**Return contract (from the brief, FACT).**
- Banking metrics must not be treated as universal.
- Unavailable and not-applicable states must be returned explicitly, never as numbers.
- The prototype's nulls for banks and Financials (above) are the starting list of "not applicable" cells.

**Magic Formula note (FACT, prototype 855).**
- The prototype ranks by EV/EBITDA, where Greenblatt uses EBIT/EV.
- It ranks across all non-financial listings before the preset's universe filter (`capMin 5`) is applied, so "Top 20" can return fewer than 20 rows.
- The ranking universe is a product decision.

---

### C.4 Measured facts on the two derivable dividend metrics

**FACT (`evidence/fundamentals_universe/corp_action.txt`).**
- `idx_event_annotation` holds 5,301 DIVIDEND events.
  - Ex-dates run from 2009-01-20 to 2026-11-03.
  - `amount_per_share`, `currency` (all IDR) and the cum / ex / record / pay dates are 100% filled.
  - The table covers 628 tickers.
- Of the 844 universe stocks:
  - 568 have at least one dividend;
  - 374 had an ex-date in the trailing 365 days to 2026-10-27;
  - 314 paid in 5 or more distinct calendar years.
- Sample trailing yields: ADRO 10.71%, ASII 8.42%, BBCA 7.78%, BBRI 11.93%, ITMG 7.02%, PTBA 3.61%, TLKM 10.43%, UNVR 14.41%.

**Caveats.**
- FACT: the payload fields `dividend_value_adjusted` and `dividend_fiscal_year` are 0 (BBCA 2020-2026). Amounts are as announced, with no split adjustment and no fiscal-year mapping.
- FACT: stored prices mix adjusted and raw history.
  - PBSA is raw across its 2026-10-14 1:2 split (845 → 384).
  - RAJA looks adjusted across its 2026-07-16 1:5 split (920 → 875).
  - ERRORS D22 records the mixed adjustment (OPEN).
  - A yield computed as an announced amount ÷ a price on another basis would be wrong across a split.
  - Evidence: `evidence/fundamentals_universe/split_check.txt`; EXEC.md:8244-8246; `audit/verify_feature04.json` F04-23.
- FACT: the table was first loaded on 2026-10-25 (`first_seen_at`). Load time cannot serve as historical availability.
- INFERENCE: the sample yields include special dividends and were not validated against an independent source. Some look high (BBCA 20 IDR on 2026-06-17 and 25 IDR on 2026-08-31).

---

### C.5 Fundamental and combined presets

| Preset | Conditions (prototype) | Runnable today | Blocked by | Label |
|---|---|---|---|---|
| Graham Defensive | pe < 15, grahamRatio < 1, der < 1, divYears > 4, epsG3y > 0 | No (1 of 5 derivable) | Statements. `der` is null for banks, so banks are silently excluded. | FACT |
| Piotroski F-score ≥ 7 | piotroski > 6, pb < 3 | No | Statements | FACT |
| Magic Formula (Greenblatt) | magicRank < 21; universe capMin 5, exclude Financials | No (only the sector exclusion runs) | Statements, market cap | FACT |
| Quality Compounder | roe > 15, der < 0.8, netMargin > 10, epsG3y > 8 | No | Statements (banks excluded through `der`) | FACT |
| High Dividend | divYield > 5, payout < 85, divYears > 4 | Partial (2 of 3) | `payout` needs net income | FACT |
| GARP | peg < 1, epsG > 15, roe > 12 | No | Statements | FACT |
| Deep Value | pb < 1, 0 ≤ pe ≤ 10 | No | Statements | FACT |
| Bank Quality | roe > 12, npl < 3, car > 18, casa > 60; universe industries [Banks] | Universe yes (48 banks); metrics no | Bank ratios | FACT |
| CANSLIM-lite (Combined) | epsGq > 20, epsG3y > 10, hi52 > −20, rs_rank(252) > 70, roe > 12 | Technical half only | Statements | FACT |
| Quality + Foreign Inflow (Combined) | roe > 15, der < 1, fnet(20) > 0, close > MA50 | Flow and technical half only | Statements | FACT |
| Value + Accumulation (Combined) | pb < 1.5, pe < 12, bandar acc(10, 3) | Flow half only | Statements | FACT |

PROPOSED (audit input, `audit/fundamentals_universe.md` P2):
- Offer only dividend yield (TTM by ex-date) and years of dividends, after a sample validation against an independent source and a split-adjustment rule.
- Show every other Fundamental metric and preset as "requires fundamental data". The AGENTS.md gate rules apply to any refusal text.
- Ship "High Dividend" only as a labelled variant without payout, if the user agrees.

---

### C.6 Point-in-time requirements

**For "today" screens, each fundamental value must carry (PROPOSED, from A2.7, Part C, `external.py` and onboarding §2.2):**
- the report it comes from: `fiscal_period_end`, period type (Q1 / H1 / 9M / FY; cumulative or de-cumulated), consolidated or parent, audited or not;
- its publication or filing date and its `available_at` time;
- the reporting currency and scale;
- the TTM construction rule;
- the share count used for per-share values (weighted or period-end), adjusted for splits after the period end;
- the price of the last **final** session, on the same split basis as the shares.

The UI shows "period X, published Y" and flags stale reports.

FACT: `IDX_Stock_Universe."Fundamental Currency"` = IDR for all 844 stocks. That is a TradingView attribute. Whether coal miners that report in USD are converted is UNKNOWN.

**For historical (point-in-time) screens and any Screen Performance History (PROPOSED):**
- join on the availability (filing) date, never the period end;
- keep vintages, so a restatement does not overwrite what was known at date D;
- use shares as of D (EXEC-MCAP Part B gives quarterly approximations that can lag up to one quarter);
- use the universe as of D.

**Facts that limit historical screens today (FACT).**
- Sector history exists only from 2026-09-28. `IDX_Stock_Universe_History` has 851 rows. Its only later changes are XCID / XCIS / XSPI `0` → `Undefined`, and IHSG added on 2026-10-23.
- There is no index, board or notation history.
- **Survivorship.** The price table holds exactly the 845 universe tickers; a loose index scan finds 0 tickers outside the universe, so delisted stocks are absent (`evidence/fundamentals_universe/survivorship.txt`). F03 on 2026-10-27 shows 37 Regular-board tickers outside the universe (ETFs, plus AKKU, CRAB, GTBO, TRUE, UNSP).
- Dividends are usable as of their `ex_date`; true announcement availability would need `dividend_created` (INFERENCE).
- The brief forbids projecting today's fundamentals or universe membership backward unless the UI labels the result as non-point-in-time and the product owner approves it. No fundamental history exists to avoid that.

---

### C.7 Universe tables and live values

**`IDX_Stock_Universe` (845 rows) (FACT, `evidence/fundamentals_universe/columns.txt`, `evidence/fundamentals_universe/universe_counts.txt`, `evidence/fundamentals_universe/universe_industries.txt`).**
- Columns: Region, Country, Company Name, Ticker (PK), Exchange, TradingView Symbol / URL, Security Type, Type Specs, Is Common Stock, TradingView Country, Currency, Fundamental Currency, ISIN, Sector, Industry, `price_feed_daily` (NULL on all 845 rows).
- 844 rows are `stock/common` in IDR; 1 is `index` (IHSG).
- **No** board, index membership, listing date, notation, shares or market cap.
- Sectors (12 values): Consumer Cyclicals 139, Consumer Non-Cyclicals 122, Financials 100, Basic Materials 93, Properties & Real Estate 79, Energy 78, Infrastructures 56, Industrials 56, Technology 41, Healthcare 39, Transportation & Logistic 38, Undefined 4 (IHSG, XCID, XCIS, XSPI).
- XCID, XCIS and XSPI are DIRE real-estate funds typed `stock/common` (recorded 2026-10-28 as ERRORS D30).
- Industry: 58 real values + `Undefined`. The AI catalog marks it "Current-state reference data; not point-in-time".

**`IDX_Stock_Universe_History`.** Bitemporal (`valid_from/to`, `recorded_from/to`, `pit_valid_from/to`, `available_at`, `capture_id`, `source_provenance`), starting 2026-09-28. FACT.

**`Universe_Equity_Description` (844 rows).**
- Sector and Industry are **swapped**: BBCA Sector = "Banks", Industry = "Financials"; ADRO Sector "Coal", Industry "Energy".
- The 2026-09-12 swap fix (D01) touched only `IDX_Stock_Universe`.
- The table is in the AI backend's table list (`apps/market-ai-backend/app/tools.py`, per ERRORS D23).
- FACT (D23, OPEN).

**`Feature_01_Stock_Daily`.**
- Holds date, ticker, close, volume, sector, industry, returns, volatility, `volume_avg_20d` (unit Shares), highs and drawdowns.
- **No** traded value, market cap or shares.
- 828 tickers on 2026-10-27; starts 2018-01-02.
- FACT.

**`Price_Stock_Indonesia_IDX`.**
- OHLCV, source metadata and `is_final`, 2018-01-02..2026-10-27; 829 rows on 2026-10-27.
- **No** value, market-cap or shares column.
- `AI_column_catalog.unit` is blank for close and volume (ERRORS D07, OPEN).
- A session without trades has no row; there are 0 zero-volume rows on 2026-10-27.
- INFERENCE (strongly supported): volume is in shares, not lots. close × volume matches F03 IDR value at a ratio of about 1.0, and price volume = Regular F05 `buy_lots` × 100 exactly (APPENDIX B, B.2).
- FACT: 150,797 rows across 181 tickers have non-integer OHLC (split-adjusted history).

**`Feature_03_Stock_Broker_Daily`.**
- `total_buy_value` / `total_sell_value` per (date, ticker, `market_board`), 2016-01-04..2026-10-27.
- The `market_board` CHECK is Regular / Nego / Tunai: these are **trading** boards, not listing boards.
- FACT.

**Prototype vs DB names (FACT).**
- All 11 prototype sectors equal DB values; the DB adds `Undefined`.
- Only 14 of 31 distinct prototype industry labels exist in the DB; 17 are prototype-only (e.g. Telecommunication, Utilities, Heavy Constructions, Food & Beverage, Retailing, Real Estate, Software & IT Services).
- Of the 94 prototype tickers, 93 are in the universe; WIKA is not. Of the 93, sectors match for 92 (SIDO: prototype Consumer Non-Cyclicals, DB Healthcare / Pharmaceuticals) and industries for 43.

---

### C.8 Universe filters: real source or missing data

Prototype code: `freshUniverse` 1141, `inUniverse` 1160-1174, `QF` 1258-1263, `usec` 1265-1277, `CAPB` 1257. The default universe is `{advMin: 1, priceMin: 50, ffMin: 0, exclNotation: true}`, with everything else empty.

| Filter | Prototype field and default | Served by existing data? | Real source and coverage (measured) | Class | Label |
|---|---|---|---|---|---|
| Index LQ45 / IDX30 / IDX80 / ISSI | `indexes` [] | **No** | No table or column; no repository reference | New data (effective-dated constituents) | FACT |
| Listing board Main / Development | `boards` [] | **No** | `market_board` (Regular / Nego / Tunai) is the trading board and must not be used | New data | FACT |
| Sector include / exclude | `sectors`, `sectorsEx` | **Yes** | `IDX_Stock_Universe."Sector"`; counts in C.7; `Undefined` set apart (backtest-worker `terminal.ts:156` classification) | Available (current state only) | FACT |
| Industry | `industries` | **Yes** | `IDX_Stock_Universe."Industry"` (58 + Undefined); the list must come from data, not the prototype labels | Available | FACT |
| Market cap min/max; buckets Mega ≥ 200 T, Big 50-200, Mid 10-50, Small 1-10, Micro < 1 | `capMin` / `capMax` '' | **No** | After EXEC-MCAP "go": `market_cap` on price rows, 820 of 844 stocks; history only through Part B (779 stocks) | New data (planned) + decision (bucket thresholds are prototype values) | FACT |
| ADV ≥ Rp B over 20 sessions | `advMin` **1** | **Yes** | Σ(close × volume) over the last 20 IHSG sessions ÷ 20 (window 2026-09-30..2026-10-27). 840 stocks have ≥ 1 bar; 395 ≥ 1 B; 211 ≥ 5 B; 145 ≥ 10 B. Against F03 Regular `total_buy_value`: median ratio 1.0001 (p5 0.966, p95 1.018). 396 ≥ 1 B on Regular value; **431 ≥ 1 B with Nego and Tunai**. 48 stocks have fewer than 20 bars. Absolute difference (verifier): 20-session median 0.67%, p90 2.57%, max 15.3%; 2 stocks cross the 1 B threshold. | Available + decision (board; days without a bar: ÷ 20 or mean over traded days; window) | FACT (`evidence/fundamentals_universe/adv_dist.txt`, `evidence/fundamentals_universe/value_check.txt`; `audit/verify_flow.json` row correction) |
| Price ≥ Rp | `priceMin` **50** | **Yes** | Last close: 83 stocks < 50. Default universe (price ≥ 50 and ADV ≥ 1 B) = **353** stocks. | Available + decision (stale last bar: P4, decided 2026-10-28) | FACT |
| Free float ≥ % | `ffMin` 0 | **No** | — | New data (or extend the EXEC-MCAP plan) | FACT |
| Exclude special notation / FCA | `exclNotation` **true** | **No** | No source. Proxy "no bar on the last session": 16 stocks on 2026-10-27 (BIKE, BSWD, IGAR, MASB, MPRO, MSIN, TFCO, TGKA and TRUK in the last 2 weeks; ADHI, CSMI, INPS, IPAC, PPGL, PTPP and XSPI older). That proxy is suspension or no trade, not notation (INFERENCE). | New data + decision: as shipped, the default-on filter would be a silent no-op | FACT |
| Metric filters | `fund` [] | per metric | The indicator engine for technical and flow; fundamental metrics are blocked as in C.3 | per metric | FACT |
| Listing age (not in the prototype) | — | No exact source | Proxy: first price bar, censored at 2018-01-02. 384 stocks start exactly on 2018-01-02; 208 in 2018-2020; 179 in 2021-2023; 66 in 2024-2025; 7 in 2026. Broker data starts 2016-01-04. | New data / decision | FACT |
| Security type (implicit) | — | Yes | `"Security Type" = 'stock'` (844); the DIRE funds XCID / XCIS / XSPI are in it with sector `Undefined` (ERRORS D30) | Available + decision (P15 a, decided with the go: included, unclassified counted apart) | FACT |

**Staleness (FACT).** 16 universe stocks have their last price bar before 2026-10-27 (ADHI 2026-08-21 … MSIN / TGKA 2026-10-26). A "latest" filter on price or ADV reads stale values for them unless an as-of rule is set (`evidence/fundamentals_universe/last_price.txt`; `audit/feature04.md` section 8). Decided (P4, 2026-10-28): each ticker is evaluated at its own last bar; stale tickers are hidden by default by the chip "Traded on `E`" and shown with the remark `STALE` (TARGET ARCHITECTURE §6.5, §6.12).

---

### C.9 Coupling with the Backtest reference file

| Statement | Label | Evidence |
|---|---|---|
| The publisher writes `ref/tickers.json.gz` from `IDX_Stock_Universe` with columns ticker, name, type, sector and industry. Its comment says every column after ticker, name and type is a classification the Backtest offers as a portfolio filter. | FACT | `apps/terminal-publisher/publisher.py:96, 416-423` |
| The backtest worker turns every extra column into a portfolio-picker grouping, and treats a non-string value as unclassified | FACT | `apps/backtest-worker/src/terminal.ts:156, 622-630`; `catalog.ts` `groupingsOf` |
| Adding board or index columns to that file would change the Backtest picker. A numeric column (market cap, ADV) would appear as a grouping with every stock unclassified. | INFERENCE | above; `apps/edge-bff/backtest/CONTRACT.md:700` (PF6) |
| Keep numeric screener attributes in a separate reference file or endpoint; reuse sector and industry from the existing file as they are | PROPOSED | `audit/fundamentals_universe.md` P5 |

---

### C.10 Data defects relevant to this appendix

| Defect | Status (ERRORS on the branch, 2026-10-28) | Label |
|---|---|---|
| `Universe_Equity_Description` Sector and Industry swapped | ERRORS D23, OPEN | FACT |
| Mixed split adjustment in `Price_Stock_Indonesia_IDX`: PBSA raw across its 2026-10-14 split (named in D22); FORU across its 2026-09-22 rights issue (found by the Feature 04 verifier; within D22's stated class of splits, bonus shares and rights) | ERRORS D22, OPEN (FORU and the derived count added 2026-10-28) | FACT |
| DIRE funds XCID, XCIS, XSPI typed `stock/common` | ERRORS D30, OPEN (recorded 2026-10-28) | FACT |
| 37 F06 Regular tickers outside `IDX_Stock_Universe` (ETFs plus AKKU, CRAB, GTBO, TRUE, UNSP) | ERRORS D29, OPEN (recorded 2026-10-28) | FACT |
| No price row for any stock on 2026-09-17 and 2026-09-18 | ERRORS M238, OPEN | FACT |
| Dividend amounts not split-adjusted; no fiscal-year mapping | Not recorded as an error | FACT |
| Price-table `volume` and `close` units blank in `AI_column_catalog` | ERRORS D07, OPEN | FACT |
| WIKA (a prototype ticker) absent from the universe and price tables | Prototype issue, not a DB defect | FACT |

---

### C.11 Product decisions surfaced by this area (audit input)

Where each is settled (UNKNOWNS / PRODUCT DECISIONS): 1, 2, 8, 9 → P11 (open) and U11; 3 → P11 and EXEC-MCAP's own go; 4 → ADV = `liquidity()`, close × volume over 20 bars, the Backtest definition (TARGET ARCHITECTURE §6.12); 5 → P4, DECIDED 2026-10-28 (hidden by default, shown with a remark); 6 → P11 (a) disabled with reasons and P22 item 7 (notation default off, decided with the go); 7 → P15 (a), decided with the go; 10 → P14 (open; "today only" fundamentals, §6.13); 11 → P11 and U8.

1. **Fundamentals source and licence.** A TradingView field set, Stockbit, IDX statements or a vendor; or no fundamentals in version 1.
2. **Fundamentals tab.** Ship it partly (dividends only) or hide it until data exists.
3. **Market cap.** Give EXEC-MCAP its go, and set the bucket thresholds. Decide whether free float joins the same plan.
4. **ADV definition.** Regular board or all boards (396 vs 431 stocks ≥ 1 B); days without a bar (sum ÷ 20 or mean over traded days); the window.
5. **Stale stocks.** Keep or exclude stocks without a recent bar.
6. **Index, board, notation and free-float filters.** Hide them, disable them with a reason, or approve new data. Change the prototype's default `exclNotation: true`.
7. **DIRE funds and `Undefined` sector rows.** Include or exclude.
8. **Bank metrics.** Whether to support them, and their definitions (NPL gross or net; LDR variant).
9. **Metric definitions.** TTM or FY; negative P/E; the D/E definition; Magic Formula (EBIT/EV vs EV/EBITDA, and the ranking universe); Piotroski for banks.
10. **Point-in-time scope.** "Today only" fundamentals, or historical screens. Historical screens also need vintages, filing dates and delisted stocks.
11. **Dividend rule.** Whether special dividends are included, and how amounts are split-adjusted.
