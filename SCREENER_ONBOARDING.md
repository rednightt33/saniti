# EDGE Screener: how it works, and how to onboard a new indicator or dataset

How the EDGE Screener works, from the rows in PostgreSQL to what the browser page draws (Part 1), and what to check in
every layer when you add an indicator, a metric or a whole dataset (Part 2): technical, flow, fundamental, macro or a
universe attribute. Written for the next agent or person who onboards something new. Read Part 1 once, then follow the
Part 2 checklist for your data class.

The user asked for it on 2026-10-28 (`EXEC.md` EXEC-SCREENER): "nanti siapkan dokumentasi sama how screener ini works
dan workflow kalau mau tambah indikator (apa requirementnya di postgres, table apa yang harus disiapkan) goalnya adalah
MD itu bisa dijadikan onboarding documents apa yang mesti di cek di service dll to onboard new documents (bukan hanya
technical, tapi ada macro juga dll)".

- **Status: Phase 1 is built on the branch and reviewed; nothing of it is deployed (2026-10-29).** Built: the
  publisher's cross-sectional (xsection) files, terminal-api's `xsection` index and `POST /xsection`, the screener core,
  the new `screener-worker`, the edge-bff module with its migration (not applied) and the page. Reviewed: the
  core/worker integration (local end-to-end on the real price history against an independent oracle), an adversarial
  semantic review and a performance review (`verification/screener/BENCHMARK_LOCAL.md`, LOCAL). The dev deploy follows
  the deploy runbook the lead holds (the user chose "A" for the deploy, commit `51bf032`). Phase 1b (Send to Backtest),
  Phase 2 (flow) and Phase 3 (presets with a bandar leg, after P9) are not built and are marked so. **When Phase 1
  lands on dev, change each BRANCH below to FACT with its deployment ID or measurement, in the same change.**
- **Verified against:** branch `claude/charming-hamilton-faq25e` on 2026-10-29 (commit `95526d5` plus the follow-up
  edits of that day), every `path:line` below re-read on that tree; the approval-gate report
  `verification/screener/AUDIT.md` (cited by section name: TARGET ARCHITECTURE 6.x, PAGE LOAD SEQUENCE 6c.x,
  MULTI-USER SCALE AND COST 6d.x, DATABASE / FEATURE CHANGES 7.x, API CONTRACT 8.x, TEST PLAN 10b.x, PERFORMANCE
  BENCHMARK PLAN 11b.x, UNKNOWNS / PRODUCT DECISIONS 13.x, FLOW INDICATOR PROPOSALS 16.x, APPENDIX C); the records
  `verification/screener/F04_PARITY.md` and `verification/screener/BENCHMARK_LOCAL.md`; read-only live PostgreSQL
  checks of 2026-10-28 where a line says "live".
- **Pointers** are `path:line` plus the symbol. `path` is a repository path, or a file name this `##` section spelled
  out before, or one only a single file has, or, among several, the one whose cited first line holds the symbol; a bare
  `:line` is in the file the section named last; the symbol written next to a pointer is on its first cited line.
  `apps/screener-worker/tests/onboarding_pointers.test.ts` (in the worker's `npm test`) reads every pointer by this rule
  and fails naming the line to change when the code moves; a pointer without a symbol is checked for its file and lines
  only. Lines move: when a line does not match, search for the symbol.
- **Labels.** FACT: in code on `main` or deployed, in data, or in a recorded measurement. BRANCH: built on the working
  branch with its tests passing, not deployed and not verified live. LOCAL: measured in the build sandbox, not on
  Railway (the Phase 17 benchmark on the dev service replaces it). PROPOSED: designed, not built. PHASE 1b / PHASE 2 /
  PHASE 3: belongs to that later phase. INFERENCE: derived, not stated or implemented directly. DECIDED: a user
  decision, with its date. OPEN: a known problem or a question without an answer. TEMPORARY: a stopgap a user decision
  allowed for now.
- **Where the other details live:**
  - `BACKTEST_END_TO_END.md`: the rack (publisher, bucket, terminal-api, its keys and service accounts) and the
    Backtest, which the Screener reuses. This document does not repeat its sections 3 to 6.
  - `apps/edge-bff/backtest/CONTRACT.md`: the Backtest's rules. `apps/edge-bff/screener/src/core/contract.ts`: the
    Screener's wire contract (types and constants). `apps/screener-worker/CONTRACT.md`: what the worker promises
    edge-bff. `apps/screener-worker/README.md`: the worker's layout, refresh, admission, caches, variables (with the
    proposed dev values), logs and tests.
  - `ERRORS_AND_SOLUTIONS.md` Part A: the data-format standard every new source must meet; Part C: the risks of macro
    and cross-asset data.
  - `NEW_TABLE_ONBOARDING_PLAN.md`: how a table becomes visible to the AI (a separate onboarding, section 2.10 below).
  - `DATABASE_CATALOG.md`: catalog roles and the mandatory maintenance after any schema change.
  - `EXEC.md` EXEC-SCREENER: the approvals and the decisions P1 to P34.
- **When this document and the code disagree, the code wins.** Fix this document in the same change.

---

# Part 1 — How the Screener works

## 1.1 The pipeline at a glance

```
 PostgreSQL (Railway "Postgres", sfo)            upstream writers: idx-price-cron (prices, 17:00 WIB),
   Price_Stock_Indonesia_IDX, IDX_Stock_Universe,    stockbit-updater (broker rounds, no schedule),
   idx_event_annotation, Feature 05 (Phase 2: F06    stockbit-event-annotation (corporate actions)
   or F03 through a new read group)
        │ read-only login terminal_publisher_login
        ▼
 terminal-publisher ── 07:30 and 19:00 WIB ──▶ bucket terminal-display (sin), prefix v1/
   per-ticker files, packs, manifests ............ unchanged for the Screener (Terminal, Backtest)
   ref/tickers.json.gz (name, type, sector, industry) + its content-keyed copy (refs) ... reused by the Screener
   + xsection/price.<sha16>.json.gz, xsection/actions.<sha16>.json.gz ........ BRANCH, Phase 1
   + xsection flow files ...................................................... PHASE 2, PROPOSED
   state.json (written last) with its `xsection` index ........................ BRANCH
        ▲ bucket credentials (terminal-api only reads and presigns)
 terminal-api (sfo): GET /state + `xsection` (BRANCH); POST /xsection (BRANCH; screener-worker key or gateway key)
        ▲ x-terminal-proxy-key, private network
 screener-worker (BRANCH, new private service, Node 22, sfo; not created on Railway yet)
   per publication: download the xsection files it lacks, verify sha256, build the snapshot on a builder thread
   (113 pinned series: the 53 indicators at start parameters, the declared derived series, the presets' series;
   universe rows and P4 remarks), install on every compute thread, compute the presets, swap all-or-nothing;
   per request: owner lanes and budgets, then the core's planner on K compute threads; result and counts caches
        ▲ x-screener-worker-key + x-screener-owner, private network
 edge-bff (FastAPI, BRANCH): /api/v1/screener/* (session cookie; Origin + CSRF on writes); relays gzip bytes;
   saved screens, My metrics, one watchlist in edge_bff tables (migration BRANCH, not applied)
        ▲ same origin
 browser: EDGE /screener → frame /screener-app/ (BRANCH): renders only, no formula code,
   connect-src 'self' (never the bucket)
```

In one paragraph: the Screener reads no market table at request time. Twice a day the existing terminal publisher,
besides the per-ticker files the Terminal and the Backtest read, writes two whole-universe ("cross-sectional",
xsection) files and names them in `state.json`. The private `screener-worker` notices the new publication through
terminal-api's `/state`, downloads only the files neither of its caches holds, checks their sha256, cross-checks every
ticker against its manifest, and computes every pinned series for every ticker once, in memory. A screen is then
mostly lookups: custom parameters are computed on demand only for the tickers that can still match. edge-bff
authenticates the browser and relays the worker's answers as bytes; it stores only the user's own objects (saved
screens, My metrics, the watchlist). The page draws what it is given. Terminal, Backtest and Screener therefore show the
same publication of the same data.

## 1.2 Parts, where they run, what they hold

| Part | Code | Status | Runs as | Holds | Never |
|---|---|---|---|---|---|
| Market tables | `database/migrations/`, `DATABASE_SCHEMA.md` | FACT | Railway `Postgres` (sfo) | the source rows | — |
| terminal-publisher | `apps/terminal-publisher/publisher.py` | FACT; the xsection writer BRANCH (`publish_xsection`, `publisher.py:735`) | Railway cron, CLI upload, sfo | read-only DB login, bucket write credentials | serves readers |
| Bucket `terminal-display` | written by the publisher | FACT | Railway bucket, sin | every published file | — |
| terminal-api | `apps/terminal-api/app/` | FACT; `xsection` on `/state` and `POST /xsection` BRANCH (`bucket.py:51` `xsection_index`, `main.py:548` `xsection`) | FastAPI, CLI upload, sfo | bucket credentials, quotas, audit and service accounts (schema `terminal`) | streams a data file |
| Shared formulas | `apps/edge-bff/terminal/src/calc/indicators.ts`, `terminal/src/data/indRegistry.json` | FACT, unchanged by the Screener | TypeScript, imported | the 53 indicator formulas and their registry | — |
| Backtest shared core | `apps/edge-bff/backtest/src/core/` | FACT, unchanged by the Screener | TypeScript, imported | parameter contract (`registry.ts`), `Calc`, `compare`, patterns, file decoding (`datafile.ts`) | — |
| Screener core | `apps/edge-bff/screener/src/core/` (18 files) and its generator `apps/edge-bff/screener/scripts/build-screener-registry.mjs` | BRANCH | TypeScript imported by the worker; the page imports only `contract.ts` and `universe.ts` | contract, registry and metric catalog, validation, series path, transforms and patterns, evaluation, planner, universe and cross-section rules | defines an indicator formula |
| screener-worker | `apps/screener-worker/` (`src/` 12 files, `Dockerfile`, `README.md`, `CONTRACT.md`) | BRANCH (DECIDED P3 a, 2026-10-28); the Railway service does not exist yet | Node 22, GitHub `main`, sfo, private | `TERMINAL_PROXY_KEY`, `SCREENER_WORKER_KEY`, the in-memory snapshot and its caches | Postgres or bucket credentials |
| edge-bff Screener module | `apps/edge-bff/app/screener.py`; migration `database/migrations/20261028_001_edge_bff_screener.sql` | BRANCH; migration not applied (not in `APPLIED.sha256`) | FastAPI, GitHub `main` | the relay, saved items (`edge_bff.screener_items`, `edge_bff.watchlist_items`) | computes a screen, stores market data |
| Page | `apps/edge-bff/screener/src/` (Vite + TypeScript, built into `static/screener-app` by `apps/edge-bff/Dockerfile`) | BRANCH | static files in edge-bff at `/screener-app/` | nothing secret | formula code, rack downloads |
| Feature 04 | `features/feature04/`, `apps/feature-04-worker/` | FACT, unchanged (DECIDED P2 a) | its own worker | stored indicators for the AI | read by the Screener at run time |

## 1.3 Rules that shape every part

From the user's decisions (DECIDED 2026-10-28, `EXEC.md` EXEC-SCREENER) and the design invariants (TARGET ARCHITECTURE
6.1). Every onboarding must keep them true.

1. **One source, the rack (P1 a).** Market data reaches the Screener only through files of the 07:30 / 19:00 WIB
   publication. No request reads PostgreSQL market tables. The Screener shows exactly the session the Terminal and the
   Backtest show; between the price cron (17:00 WIB) and the end of the 19:00 run the database holds a session the rack
   does not (about 3 hours, TARGET ARCHITECTURE 6.5).
2. **One formula path (I1).** Every technical number comes from `F` in `indicators.ts` through the Backtest core's
   `Calc` (`apps/edge-bff/screener/src/core/metrics.ts:250` `series`, the one path). There is no SQL, TA-Lib or Python
   copy of a formula. The page side is locked by a test (`apps/edge-bff/screener/tests/bundle/bundle.test.mjs`, "import
   from the screener core only contract.ts and universe.ts, and no formula module"); in the core the rule is stated in
   `transforms.ts`' header and held by review: no test fails when a core file defines an indicator kernel (OPEN).
3. **The Backtest is untouched (I3).** No byte changes in `indicators.ts`, `indRegistry.json`, `backtest-registry.json`
   or `apps/edge-bff/backtest/src/core/**` during the Screener build; `apps/backtest-worker/**` changes only as a
   recorded approval says (EXEC-MU-RUNTIME: `scripts/screener/backtest_worker_baseline.json` names the approved worker
   tree, its versions and the EXEC section; any other worker change fails the tripwire). Why: the Backtest's
   `engine_version` hashes every core file (`apps/backtest-worker/src/version.ts:18-21`, `SOURCES`) and its
   `registry_version` hashes `indRegistry.json` plus `indicators.ts`
   (`apps/backtest-worker/scripts/build-registry.mjs:25`, `registryVersion`); either change alters every Backtest result
   key, and a stale registry stops the backtest worker at start (`apps/backtest-worker/src/server.ts:403`,
   `registry_mismatch`). The tripwire `scripts/screener/check_backtest_untouched.mjs` (BRANCH; `npm run tripwire` in
   `apps/edge-bff/screener`) fails on any of that against `origin/main`, also for `features/feature04`,
   `apps/feature-04-worker` and `apps/stockbit-updater` (`PROTECTED`). New indicators therefore arrive only through a
   deliberate **registry release** (P6, section 2.4).
4. **Feature 04 is unchanged and is not read at run time (P2 a).** It is the parity oracle in tests (section 1.12).
5. **Nothing fabricated (I5).** Every cell is PASS, FAIL or NA, and every NA carries a reason code
   (`contract.ts:214` `NA_REASONS`). A metric without data is shown disabled with its reason, never silently dropped.
6. **No silent adjustment (I7).** Invalid input is refused with the field and the fix; never clamped, rounded or
   reordered (`validate.ts` header; `registry.ts` header: the backtest core's `resolveParams` first, then only
   narrowing).
7. **Versions in every answer (I6).** Each answer names the data, engine and registry versions that produced it (section
   1.13); every computed answer opens with them (`apps/screener-worker/src/run.ts:304-312`).
8. **Stale tickers and unadjusted price breaks are hidden by default (P4, P4.1 A).** Both chips default on: absent
   means on (`universe.ts:56`, `traded_on_eval_date !== false`, `exclude_price_breaks !== false`). Shown through a chip,
   their rows carry a remark with the reason (`STALE` with the last bar date; `PRICE_BREAK` with the action, ex-date,
   ratios and the close ratio, `universe.ts:92` `priceBreakRemarks`), and their price-derived values stay visible:
   a cell whose lookback contains an ex-date carries `PRICE_BREAK_IN_LOOKBACK` (`evaluate.ts:186` `priceBreakRemark`),
   and the answer warns `PRICE_BREAKS_IN_RESULT` with the rows and cells. A remark never changes PASS, FAIL or NA.
   Tests: `apps/screener-worker/tests/server.test.ts` "P4: stale and price-break tickers are hidden by default and
   counted; shown through the chips, they carry their remarks and their values ...", `tests/core/universe.test.ts`
   "priceBreakRemarks", `tests/core/lookback.test.ts` "PRICE_BREAK_IN_LOOKBACK at the edge of each lookback".
9. **Flow uses all boards by default (P8 b)**, with a labelled Regular variant (PHASE 2).
10. **The user's objects live in `edge_bff` tables (P12 a)**: saved screens, My metrics, one watchlist.
11. **Multi-user and cost (P29-P34).** EDGE users are external. What depends only on the publication is computed once
    and shared by every user; nothing user-specific enters a shared cache; every stored row and every limit is keyed by
    the owner; per-owner compute limits are built in Phase 1 (P33). Details in section 1.16. **Page load** follows the
    Terminal and Backtest pattern: draw at once, load what is needed, use answers kept per publication (section 1.9).

## 1.4 Stage 1: PostgreSQL

The Screener never queries PostgreSQL for market data. What it uses reaches it through the publisher, which reads with
the read-only login `terminal_publisher_login` (member of `terminal_market_reader` only;
`default_transaction_read_only on`, `statement_timeout 120s`, connection limit 4:
`scripts/provision_terminal_logins.py:15-31`).

| Table | Read by the publisher | Used by the Screener for | Phase |
|---|---|---|---|
| `Price_Stock_Indonesia_IDX` (`timeframe = 'Daily' AND is_final`) | per ticker-year (`PRICE_SQL`, FACT), and for the `price` xsection file one statement without the ticker filter (`XSECTION_PRICE_SQL`, `publisher.py:129`, BRANCH): a Seq Scan of 1,331,548 rows, 49,339 buffers, 5.3 s on dev, `EXPLAIN (ANALYZE, BUFFERS)` 2026-10-28, ordered in Python because `ORDER BY` spilled 86 MB (`publisher.py:124-128`) | whole-universe bars | 1 |
| `IDX_Stock_Universe` | the reference file `ref/tickers.json.gz` (`UNIVERSE_SQL`, `publish_refs`, `publisher.py:764`) | name, type, sector, industry, read from the existing reference file (not copied) | 1 |
| `idx_event_annotation` | per-ticker events files (FACT), and for the `actions` xsection file `XSECTION_ACTIONS_SQL` (`publisher.py:141`, BRANCH): family `CORPORATE_ACTION`, role `EX_DATE`, the five price-affecting types plus `DIVIDEND`, from the first published price year | price-break remarks (P4); cash dividends (PHASE 2 dividend metrics) | 1 |
| `Feature_05_Foreign_Domestic_Broker_Detail` | per-ticker broker files (`BROKER_SQL`) | the `broker_window` file for broker-ranking metrics | PHASE 2 |
| `Feature_06_Foreign_Domestic` or `Feature_03_Stock_Broker_Daily` | **not readable** by the publisher (live L1: no SELECT on F06 or F04) | the long all-board foreign-flow series (`flow_series`); needs a new NOLOGIN read group by forward migration (migration 2, report 7.2; the source table is decision D9 of FLOW INDICATOR PROPOSALS 16.11) | PHASE 2 |

What the Screener adds to the database:

- **Migration 1 (Phase 1; BRANCH, not applied: `database/migrations/20261028_001_edge_bff_screener.sql`):**
  `edge_bff.screener_items` (`:26-43`: `item_id` `scr_` + 32 hex, kind `screen` or `metric`, name 1-120 characters,
  `definition` as `jsonb` up to 65,536 bytes, `schema_version`, `registry_version`, `screener_registry_version`,
  `definition_hash`, `revision`; index `screener_items_owner_kind_updated`) and `edge_bff.watchlist_items` (`:46-`:
  `owner_key`, `ticker`), in the house style of the `edge_bff` migrations (preflight, comments, exact grants `:65-66`, a
  `$verify$` block, the rollback as a comment). No public table changes. Its DRYRUN/APPLY jobs are prepared under
  `verification/screener/jobs/` (`run_migration.sh`, `check_migration_log.py`).
- **Migration 2 (PHASE 2):** role `terminal_publisher_feature_reader` (NOLOGIN) with SELECT on the chosen flow table,
  granted to `terminal_publisher_login` **only**. A grant to the shared `terminal_market_reader` would widen the public
  terminal-api too (live L2: both logins are members), and `provision_terminal_logins.py` refuses any login that reaches
  more or fewer relations than it lists (`LOGINS`, `reach`), so the script changes with the migration.
- **No catalog rows** (`Table_Catalog`, `Column_Catalog`, `Feature_Catalog`): no public table, column or Feature
  changes. `Table_Catalog` covers schema `public` only, and the `edge_bff` Backtest tables set the precedent of no rows
  (report 7.2).

Live facts every onboarding meets (FACT unless marked):

- 845 universe rows: 844 `stock` and the index IHSG. No delisted tickers and no historical index membership
  (survivorship; APPENDIX C.6).
- Final daily prices start on 2018-01-02; Feature 05 on 2016-01-04. On 2026-09-17 and 2026-09-18 only IHSG has prices
  (ERRORS M238, OPEN): a cell's `bars_ago` counts the ticker's own bars and `market_sessions_ago` the IHSG calendar, so
  the two differ there.
- Prices are stored as received: back-adjusted for splits before 2026-09-12, raw after it (`ADJUSTED_HISTORY_BOUNDARY`,
  `apps/edge-bff/backtest/src/core/engine.ts:157`; ERRORS D22, OPEN). Eight tickers had a price-affecting action between
  that date and 2026-10-27 (live L6, report 6.12; the local end-to-end found the same 8 price-break rows).
- Broker data trails prices until a new Stockbit token starts a round (ERRORS M243).
- The DIRE funds XCID, XCIS and XSPI are typed `stock/common` with sector `Undefined` (ERRORS D30, OPEN; Part A A1.4).

## 1.5 Stage 2: terminal-publisher

The existing publisher is described in `BACKTEST_END_TO_END.md` section 4. What matters for any new file:

- **Deterministic bytes (FACT).** `encode` (`publisher.py:238`) writes compact JSON with `allow_nan=False`, then gzip
  level 9 with `mtime=0`; equal rows give equal bytes, and the sha256 is taken over the gzip bytes. Test:
  `apps/terminal-publisher/tests/test_publisher.py` `test_xsection_files_are_deterministic_and_never_rewritten`.
- **Columnar documents (FACT).** `columnar` (`publisher.py:234`) turns rows into `{column: [values]}`; readers decode
  with `decodeColumnar` and `inflateVerified` (`apps/edge-bff/backtest/src/core/datafile.ts:67, 91`), which require a
  `columns` list of equal-length arrays and check size and sha256.
- **Content keys (FACT: ERRORS M250, deployed from PR #41 and integrated on the branch as `41f14b7`; the reference
  copies of EXEC-MU-RUNTIME T5 are BRANCH).** A changed data file, pack, xsection file or reference copy is a new object
  whose key carries its sha256 and is never rewritten with other bytes; `collect_garbage` (`publisher.py:962`) deletes
  what no manifest or index names any more, in a daily run, once the last finished run is `GC_GRACE_SECONDS` (3600,
  `publisher.py:181`) old.
- **Change detection by stamps (FACT).** A `daily` run republishes only what changed: price stamps per ticker-year,
  event stamps per ticker, broker by date (`Publisher.run`, `publisher.py:871`).
- **Write order (FACT).** Data files, packs, the xsection files, manifests, reference files and their `refs` copies,
  then `state.json` last with `finished_at`, `xsection` and `refs`; the order is `publisher.py:922-957`. terminal-api
  and the workers treat a new `finished_at` as a new publication.
- **Verify mode (FACT, extended on the branch).** `verify` (`publisher.py:1066`) compares every manifest-listed file
  with SQL (rows, first and last date, a column sum), the xsection files too (`verify_xsection`, `publisher.py:1145`),
  and exits 1 on a mismatch (`publisher.py:1257`; test `test_verify_checks_the_xsection_files`).

**The xsection file family (BRANCH).** Each whole-universe file:

| Rule | As built |
|---|---|
| Key | `v1/xsection/<name>.<sha16>.json.gz` (`XSECTION_KEY = indexed_key('xsection')`, `publisher.py:151-157`): content-addressed by the first 16 hex of its sha256, never overwritten |
| Body | one columnar document from `encode`: `schema_version`, `dataset` `xsection`, `name`, `units`, `means` (what each column and null mean), `columns`, equal-length arrays (`xsection_price_doc` `publisher.py:404`, `xsection_actions_doc` `publisher.py:425`) |
| Index | `state.json` `xsection: {name: {key, sha256, bytes, rows, as_of}}`, written before nothing else reads it (test `test_the_xsection_files_are_written_before_the_state_json_that_indexes_them`); `xsection_entries` (`publisher.py:480`) keeps exactly what terminal-api's `xsection_index` serves (test `test_terminal_api_reads_the_index_as_written`) |
| Rebuild | `XSECTION_REBUILT_BY` (`publisher.py:148`): `daily`, `backfill`, `packs` rebuild `price` and `actions`; `events` rebuilds `actions`; every other mode carries the entries forward (test `test_modes_that_do_not_rebuild_an_xsection_file_carry_its_entry_forward`). A file that fails to build keeps its previous entry, the rest of the run goes on, and the run exits 3 (`publisher.py:1267`; test `test_a_failed_xsection_file_keeps_its_entry_and_the_rest_is_published`) |
| Cleanup | `collect_garbage` deletes an xsection object the index no longer names (tests `test_pruning_keeps_the_objects_of_the_previous_index`, `test_the_xsection_cleanup_waits_for_the_grace_so_two_runs_minutes_apart_keep_the_previous_index`, `test_the_xsection_cleanup_keeps_newer_objects_other_keys_and_everything_when_no_index_names_a_file`) |
| Slices equal packs | each ticker's slice of `price` is encoded as its price pack and compared with the manifest's pack sha256; a pack that differs is republished from the slice (`xsection_price`, `publisher.py:694`; tests `test_each_ticker_slice_of_the_price_file_equals_its_price_pack`, `test_a_pack_that_differs_from_the_table_is_republished_from_the_slice`) |

Phase 1 files (BRANCH): `price` (every published ticker including IHSG from its first published year, columns
`t,d,o,h,l,c,v` ordered by ticker then date, plus `tickers: [{t, pack_sha256, first, last, rows}]` in file order;
measured locally 11,758,823 B gzip, 74,272,854 B inflated, 1,330,722 rows) and `actions` (columns `t, d, type,
ratio_old, ratio_new, amount_per_share, currency`; every action of the price-affecting types and every cash dividend
since the first published price year, future ex-dates included; the source's 0 is published as null; the readers
apply their own bounds: the price-break rule uses `ADJUSTED_HISTORY_BOUNDARY`). PHASE 2 files (PROPOSED; the metric
catalog already names them in `requires`): `broker_window` (raw F05 rows of the last 41 complete sessions) and
`flow_series` (the long all-board flow series); their final shape follows the flow indicators the user picks (FLOW
INDICATOR PROPOSALS 16.9).

## 1.6 Stage 3: terminal-api

The only holder of the bucket key. See `BACKTEST_END_TO_END.md` section 6 for its routes, keys, service accounts (6.1),
cache and quotas.

| Route | Status | Answer | Quota, audit |
|---|---|---|---|
| `GET /api/terminal/v1/state` | FACT on `main` (EXEC-BACKTEST-LOAD); the `xsection` and `refs` fields BRANCH (`bucket.py:11` `STATE_FIELDS`; `xsection_index` `bucket.py:51`, `refs_index` `bucket.py:62`) | `finished_at`, `price_through`, `broker_through`, `broker_behind_sessions`, the `xsection` index (well-formed entries only, else null) and `refs` | none |
| `POST /api/terminal/v1/xsection {names}` | BRANCH (`apps/terminal-api/app/main.py:548`; caller check `xsection_caller`, `main.py:289`) | per name a presigned URL, `sha256`, `bytes`, `rows`, `as_of`; a name not in the index answers 404 `xsection_not_published` with the indexed names | only the screener-worker's service key (`XSECTION_SERVICES`, `main.py:39`; `TERMINAL_SERVICE_KEY_SCREENER_WORKER`, EXEC-MU-RUNTIME T1) or, until a later step removes it, the gateway key; anything else 403 `gateway_only`. One audit row under the `REF` pseudo-ticker (`apps/terminal-api/app/quota.py:11`), dataset `xsection`; file quota = number of names; bytes counted |

Rules a new file must meet at terminal-api (`bucket.py:13` `XSECTION_NAME` and `xsection_index`): the name matches
`^[a-z0-9][a-z0-9_-]{0,31}$`; the index entry has exactly `key`, `sha256` (64 hex), `bytes` (≥ 1), `rows` (≥ 0) and
`as_of` (a string of at most 64 characters, else null); the key is `v1/xsection/<name>.<first 16 hex of the
sha256>.json.gz`. An entry that breaks a rule is dropped from `/state` and never presigned. A call asks at most 16
names (`MAX_XSECTION_NAMES`, `main.py:50`). Tests: `apps/terminal-api/tests/test_api.py`
`test_xsection_index_keeps_only_well_formed_entries`, `test_xsection_presigns_only_keys_of_the_xsection_family`,
`test_xsection_grants_the_indexed_files_to_the_gateway_in_one_audit_row_under_ref` and the other `test_xsection_*`.

Neither route is in edge-bff's browser allow-list (`TERMINAL_ROUTES`, `apps/edge-bff/app/main.py:35`), so the browser
can never pull a whole-universe file. **A new xsection name needs no terminal-api code change**: names are validated
against the index, not against a list in code; only the size matters for the quota (section 1.15).

## 1.7 Stage 4: screener-worker (BRANCH)

A private `node:http` service like the backtest worker: Node 22 with type stripping and the backtest worker's module
loader (`apps/backtest-worker/loader/register.mjs`, which resolves the Terminal's extensionless imports, ERRORS M249),
no npm runtime dependency, one replica in `sfo` on dev (P32: two once external users start), private network only, no
Postgres or bucket credentials. It reads the rack through terminal-api as the backtest worker does
(`TerminalClient` for files and the reference file; its own thin `TerminalApi` for `/state`, `/xsection` and
`/manifest`, `apps/screener-worker/src/refresh.ts:67`, because `TerminalClient.api` is private, `terminal.ts:414`, and
changing `terminal.ts` would change the Backtest's `engine_version`). The image (`apps/screener-worker/Dockerfile`)
keeps the repository layout under `/app` and copies only what the server reads (report 7.1). Its watch patterns must
cover its own folder, the screener core and generator, the backtest core, the terminal calc folder, `indRegistry.json`
and the borrowed backtest-worker files.

### 1.7.1 Process, threads and start-up

- **Threads** (`src/pool.ts`, `src/thread.ts`): the HTTP thread answers `/health`, `/ready`, the catalog, the universe
  and cache hits; K compute threads (`SCREENER_THREADS`) run screens, previews and counts; a builder thread is started
  for one refresh and killed after it (`apps/screener-worker/src/server.ts:247`, `:272`). Every thread runs under
  `SCREENER_THREAD_HEAP_MB` (`pool.ts:56-66`, `resourceLimits.maxOldGenerationSizeMb`): a thread that needs more stops
  alone, its request answers `500 OUT_OF_MEMORY` (`server.ts:552`), and it is started again with every snapshot
  installed before it takes work (`pool.ts:99-107`). Tests: `tests/heap.test.ts`, `tests/pool.test.ts` "a thread that
  does not stop is terminated after the grace and started again with the snapshots installed".
- **Configuration** (`src/config.ts:74-127` `loadConfig`): 30 variables, every limit without a default; a missing or
  invalid one stops the start with `config_invalid` naming the variable, never its value. The full list with the
  proposed dev values (LOCAL, provisional) is the worker README's "Configuration" table. Tests: `tests/config.test.ts`;
  `tests/readme_config.test.ts` (the README table against `loadConfig` itself).
- **Start-up check** (`src/version.ts:56-71` `checkStartup`): the screener registry has no problem against the base
  registry (`registry.ts:87` `registryProblems`); `screener-metrics.json` and `presets.json` pass `catalogProblems`
  with the transforms and patterns `transforms.ts` computes (`IMPLEMENTED_TRANSFORMS`, `IMPLEMENTED_PATTERNS`); the
  backtest registry artifact matches its sources; every source `screener-registry.json` names (except the build-only
  oracle script) is in the image with the recorded sha256. Otherwise `startup_check_failed` and exit.

### 1.7.2 Refresh: one snapshot per publication

`src/refresh.ts` `Refresher.refresh` (`:248-323`), rules in its header (`:14-32`):

1. **Poll.** `GET /state` every 60 s (`POLL_MS`, `:47`); act only on a new `finished_at`, one refresh at a time
   (`tick`, `:225`).
2. **Phase 1 files.** The index must name `price` and `actions` (`PHASE1_FILES`, `src/snapshot.ts:56`;
   `refresh.ts:264-266`, else `DATA_UNAVAILABLE`). Other indexed names are ignored by the refresh.
3. **Skip unchanged.** The same sha256 for both files and the same reference contents (`referenceHash`,
   `snapshot.ts:111`): nothing is downloaded, recomputed or swapped; only `published_at` and the state fields advance
   (`refresh.ts:268-277`, server `advance`, `server.ts:296-309`: the snapshot's cached answers and counts are dropped
   and the presets computed again, so no answer names the older publication). Test: `tests/refresh.test.ts` "the same
   files on a new publication: no download, no recompute, no swap; only published_at advances (6d.2)".
4. **Caps before any grant.** An indexed size above `SCREENER_MAX_FILE_BYTES`, or downloads above
   `SCREENER_MAX_REFRESH_BYTES`, fail the refresh before `/xsection` is called (`refresh.ts:279-288`).
5. **Grant only what is missing**, from the publication `/state` named (`refresh.ts:290-300`, `grant` `:343-356`): a
   skewed answer (terminal-api's two processes may lag each other up to a minute) is asked again
   `SCREENER_DOWNLOAD_RETRIES` times, then deferred 15 s (`SKEW_RETRY_MS`, `:48`; log `refresh_deferred`), never a
   failure. Every URL must be on `SCREENER_FILE_ORIGIN`.
6. **Build** on the builder thread (`thread.ts:86-95`): `TerminalClient.file` downloads (or reads the disk cache by
   sha256) and `inflateVerified` checks sha256 and size; `buildSnapshot` decodes (section 1.7.3).
7. **Cross-check** every ticker against its `/manifest`: rows = the sum of its yearly files, last date = their newest
   (`refresh.ts:358-367`).
8. **Pre-warm, digest, install, presets, documents, swap** (`server.ts` host `complete`, `:257-294`): the pinned series
   are computed on the builder alone while a snapshot serves, at a cold start on the builder and every compute thread
   in chunks (`:260-268`); `snapshot_digest`; install on every compute thread, all-or-nothing (`pool.ts:219-225`); the
   available presets are computed in the system lane and pinned in the result cache (`server.ts:346-360`); catalog and
   universe documents; the swap (`server.ts:322-336`). The previous snapshot keeps serving requests pinned to it for
   `SCREENER_PREVIOUS_GRACE_S`, then is dropped with its caches.
9. **Failure.** Any integrity failure keeps the previous snapshot, logs `REFRESH_FAILED` with its code, and the same
   publication is retried after 60 s doubling to 16 min; a newer one is tried at once (`refresh.ts:325-335`).

Tests: `tests/refresh.test.ts` (a publication loads; a wrong sha256 is 424 `DATA_INTEGRITY` with no snapshot and keeps
the previous one when held; manifest and reference mismatches; the caps; a restart on a warm disk cache grants
nothing; skew then deferral; skip unchanged; one refresh at a time; pinning across a swap).

### 1.7.3 The snapshot: what is computed once per publication

`src/snapshot.ts` `buildSnapshot` (`:177-288`) and `ThreadSnapshot` (`:401-464`):

- **Bars once per replica** in `SharedArrayBuffer` columns (O, H, L, C, V as `Float64Array`, a null volume as NaN, T as
  an index into one date table). Each ticker's slice goes through the backtest core's `priceSeries` (`datafile.ts:139`),
  so the Terminal's and the Backtest's row rules apply; every ticker must be in the reference file and IHSG present
  (`snapshot.ts:182-186`). F never runs on a typed view: bars are materialized back into plain arrays equal to
  `priceSeries`' (`materialize`, `snapshot.ts:314`; test `tests/typed_views.test.ts`, F bit-identical).
- **No look-ahead.** E = `state.json` `price_through` (`snapshot.ts:193`); a price file holding a bar after E is refused
  with `DATA_INTEGRITY` and the previous snapshot keeps serving (`snapshot.ts:240-244`; semantic review S3; test
  `tests/snapshot.test.ts` "no look-ahead (6.5 as-of policy) ...").
- **Universe rows** (the listed stocks, hidden ones included): name, sector, industry, last, 1D %, ADV20 (the backtest
  core's `liquidity`, `signals.ts:174`, through `metrics.ts:155` `universeAttributes`), first and last bar, bar count,
  `stale`, and the P4 remarks from the `actions` file (`snapshot.ts:221-237`).
- **Pinned series** (`snapshot.ts:259-280`): the 53 indicators at `registry.ts:249` `startParams` (the registry
  defaults, except I43 at anchor Week: P17 a does not offer its default Session), 76 outputs; the core's declared
  derived series of the default cards (`condition.ts:349` `declaredDerivedSeries`: the bar fields, the prior Donchian
  bands, the rising lags and vs-MA averages); every series the presets read. 113 series on the real publication (LOCAL).
  Each is a tail of `SCREENER_WITHIN_MAX` + 1 bars per ticker (`metrics.ts:176` `tailLength`) in one shared
  `Float64Array`, written by the pre-warm through the one `series()` path (`prewarmChunk`, `snapshot.ts:366-383`),
  installed in each thread's `SeriesCache` as pinned entries (`:433`). Test: `tests/snapshot.test.ts` "the pre-warm: ...
  each tail equal to the dynamic series() on the same bars".
- **Identity**: `price_data` = `dataVersion` over (ticker, `price`, pack sha256) of every ticker (`snapshot.ts:253`);
  `sid` = price_data + the actions contents + the reference hash (`:257`), the key of every cache; `snapshot_digest` =
  sha256 over the series keys, tickers and every tail with its header (`:386-392`): two replicas at one publication log
  the same digest. Test: `tests/snapshot.test.ts` "version stability".
- **Per thread** (`ThreadSnapshot`, `TickerView` `snapshot.ts:338-359`): each ticker's dates kept for the snapshot's
  life (about 10.6 MB per thread), price columns and the backtest core's `Calc` made on first use, `missingInput`
  answered from a per-ticker mask (`:350-355`), so a screen of pinned series reads no bar column (test
  `tests/views.test.ts`); `return_rank` cross-sections once per thread and snapshot, at most 16 windows (`crossSection`,
  `snapshot.ts:452-466`).

Custom parameters are computed per request through the same `series()` call (`metrics.ts:250`), keyed by
(`price_data`, `screener_engine`, the resolved reference) (`seriesKey`, `metrics.ts:201`), on the ticker's **full**
history then tailed (tails are not exact for recursive and cumulative indicators: EMA 200 is up to 7.7% off with a
500-bar tail, report 6.5), and kept in the thread's series LRU (one share of `SCREENER_CACHE_BYTES`). "Precomputed"
and "dynamic" are the same call at two times, so they cannot differ; each condition says which (`source`). Test:
`tests/core/screen.test.ts` "precomputed and dynamic are the same call at two times (report 6.7)".

Never offered: raw level thresholds on cumulative indicators (OBV, PVT, A/D, NVI, PVI: the level depends on the first
bar forever); lengths above the derived caps; past evaluation dates (report 6.13).

### 1.7.4 The condition engine (screener core)

Metric references (wire grammar, `apps/edge-bff/screener/src/core/contract.ts` `MetricRef`): `indicator`, `price` (a bar
field), `transform` (`pct_distance`, `band_position`, `lag`, `change`, `rolling_max`, `rolling_min`, `rising_run`, `ma`,
`ratio`, `vs_index`), `pattern` (`breakout`, `breakdown`, `volspike`, `macross`, `macd_divergence`, `squeeze`,
`stoch_cross_in_zone`, `new_high`, `silent`), `flow` (PHASE 2; refused at bind until then, `condition.ts:182`),
`xsection` (`return_rank`), `universe` (a row attribute; fundamentals use this kind too, `contract.ts:460-462`). These
lists are data, read from `screener-metrics.json` (section 1.11), never kept in code; `transforms.ts` implements each
`fn` and pattern `type` (`IMPLEMENTED_TRANSFORMS` `:152`, `IMPLEMENTED_PATTERNS` `:334`), and `catalogProblems`
(`catalog.ts:172`) fails when the two disagree.

| Test | Rule (`evaluate.ts`) |
|---|---|
| VALUE | the metric at the evaluation bar; `gt`/`lt` strict; `between` inclusive and counted as one condition; `value > value2` refused (`INVALID_CONDITION`), never reordered |
| STATE | `compare(lhs, op, rhs)[at]` of the backtest core (`conditions.ts:52`): bar 0 never true, a missing side false; lhs and rhs from a bar field, an output, a value or a second instance (SMA 50 vs SMA 200); a pattern state is its 0/1 signal at `at` |
| EVENT | a cross (both sides finite on the bar and the bar before) or a pattern signal within the last `within` bars (1 to `SCREENER_WITHIN_MAX`) on the ticker's own bars; returns `event_date`, `bars_ago`, `market_sessions_ago` (IHSG calendar) and `last_event_date`; never reduced to a state |

A bar field compared with an output whose `price_compare_lag` is 1 (Donchian's prior band, `rolling_max` of the high)
reads the lagged series `lag(x, 1)` as its own cached series, never a shifted view (`condition.ts` header).

NA reasons (per cell, never failing the whole screen; `contract.ts:214` `NA_REASONS`): `INSUFFICIENT_HISTORY`,
`NULL_AT_EVALUATION` (also for a missing input, e.g. IHSG volume), `FLOW_UNAVAILABLE`, `FLOW_LAGGED`,
`NOT_APPLICABLE` (`applies_to`), `DATA_INTEGRITY`, `MIXED_ADJUSTMENT_BASIS`. Remarks explain a value and never change
PASS, FAIL or NA: `STALE` and `PRICE_BREAK` per row, `PRICE_BREAK_IN_LOOKBACK` per cell. A cell's lookback
(`evaluate.ts:172-180`): its window for window-class series, the whole history for recursive, cumulative and calendar
ones, one bar for a bar field; an EVENT cross extends each side by `within`, an EVENT pattern by `within - 1` (its
stated window already holds the bar before; semantic review S1); every window-class pattern window is exact (S2;
test `tests/core/lookback.test.ts` "a window-class pattern reads exactly its stated window").

**As-of policy.** The evaluation date E is `price_through`. Each ticker is evaluated at its own last bar on or before E
(`evaluate.ts:79` `evaluationBar`); a ticker whose last bar is before E is STALE (hidden by default). `bars_ago`
counts the ticker's own bars. Every series a condition reads is causal (test `tests/core/asof.test.ts`).

**Match and near** (`match.ts`): `need = entryNeed(logic, at_least, active)` of the backtest core
(`conditions.ts:263`); `met` counts PASS only; `near = !match && need >= 2 && met == need - 1`
(`match.ts:23` `isNear`), one rule for the table, the preview and the CSV.

**Cross-section** (`xsection.ts`): `return_rank` ranks over a fixed population (active, non-stale stocks without a
price break, finite value at E; `rankPopulation` `:19`), fixed before any condition, so showing a hidden ticker moves no
other rank (P7); a member's denominator is P - 1, an outside ticker's P, every rank in [0, 100].

### 1.7.5 The planner

`plan.ts` (orchestration, header `:1-23`) over `screen.ts:114` `runScreen`:

| Stage | Evaluates |
|---|---|
| S0 | universe hard filters (`universe.ts:52` `applyUniverse`: type, sector and industry, price, ADV, the P4 chips, history length, explicit tickers, universe-attribute filters), then the metric filters that need a formula: conjunctive, outside `met` |
| S1 | population-level cross-sectional values (never pruned) |
| S2 | conditions whose every series is pinned, and universe attributes: every S0 survivor |
| S3 | the other conditions, cheapest predicted first (`orderS3`, `plan.ts:130`) |
| S4 | completion of every remaining cell of each surviving row |

Pruning (`pruneThreshold` `:28`, `canPrune` `:30`): θ = need − 1 when need ≥ 2, else need; a ticker with m passes and r
unevaluated conditions is pruned iff m + r < θ. It never hides a match or a near miss; ANY never prunes (warning
`NO_PRUNING_FOR_ANY`); `options.exhaustive` turns pruning off. Tests: `tests/core/plan.test.ts` "runPlan: pruned output
= exhaustive output = brute force (property test)", `tests/core/oracle.test.ts` (pruned = exhaustive = an independent
oracle on random whole screens).

**Cost and budget.** Before any compute the worker prices the worst case on the S0 survivors
(`apps/screener-worker/src/run.ts:179-206` `estimateCost`: each condition's stage; for S3 the predicted ms of its series
that are not pinned, from `costUnits` `:152-170` over the core's `costTracker`, `plan.ts:143`, which learns ms per unit
per replica with an exponential mean, alpha 0.2, `run.ts:138`, seeded by the registry's provisional 5.96 ns per bar per
length unit). Above `SCREENER_MAX_CPU_MS` the request is refused (`422 LIMIT_EXCEEDED compute_budget`, naming the
costliest condition), never cut short. LOCAL caveat (`BENCHMARK_LOCAL.md` section 7): the model under-prices an O(N)
series 24-62 times until the tracker has seen it and mispredicts up to 4.36 times after; hence the proposed
`SCREENER_MAX_CPU_MS` 4500 = 20 s / 4.36 until a fitted model lands (Phase 17).

### 1.7.6 Admission, lanes and per-owner budgets (P33, built in Phase 1)

In this order (`src/pool.ts` header `:4-23`; `server.ts:386-407` `compute`):

1. a result-cache hit (and a counts hit) is answered at once, outside every queue and budget;
2. the per-request compute budget (above);
3. the per-owner budget (`OwnerBudget`, `pool.ts:149-177`): the thread ms an owner tag used in the last 60 s plus the
   predicted ms it has waiting or running, against `SCREENER_OWNER_CPU_MS`; above it `422 LIMIT_EXCEEDED
   owner_cpu_budget` with `retry_after_seconds`;
4. the replica queue: at most `SCREENER_QUEUE` users' requests wait, else `409 BUSY`; the system lane (the presets of a
   refresh) is not counted (`pool.ts:249-255`; test `tests/pool.test.ts` and the integration's defect 7);
5. the owner's lane: at most `SCREENER_OWNER_INFLIGHT` of its requests run at once; a free thread takes the next one by
   deficit round robin across lanes weighted by predicted cost, quantum `SCREENER_MAX_CPU_MS / 4`
   (`pool.ts:328-352`; `server.ts:216`), so a heavy user slows only themself; a newer request of the same page replaces
   a waiting older one (`pool.ts:241-247`; it answers `409 SCREEN_REPLACED` or `PREVIEW_REPLACED`, `REPLACED` `:196`).

The deadline is `SCREENER_DEADLINE_MS` from arrival, queue included (`504 TIMEOUT`); a running request past it, or one
whose caller left, is asked to stop through a shared flag the planner checks between tickers, and its thread is
terminated after 1 s (`KILL_GRACE_MS`, `pool.ts:31`, `:305-316`). Tests: `tests/pool.test.ts` (inflight, round robin,
cost-weighted DRR, BUSY, replacement, deadline, kill and respawn, a caller that leaves, P33),
`tests/server.test.ts` "compute_budget: ..." and "P33: an owner over SCREENER_OWNER_CPU_MS per minute is refused with
the seconds to wait; another owner is not; a cache hit is never refused". LOCAL fairness (`BENCHMARK_LOCAL.md`
section 5): with `SCREENER_OWNER_INFLIGHT` = K a heavy owner held every thread and light owners' p95 rose 32-41 times;
with K - 1 it rose 1.6 times.

### 1.7.7 Caches and version pinning

| Cache (per replica) | Key | Bound | Code |
|---|---|---|---|
| Result cache: run and preview answers as gzip bytes with `ETag` | `resultKey`: kind, `sid`, `screener_engine`, `registry`, `screener_registry`, `definition_hash`, `exhaustive`, `explain` (preview adds the ticker); nothing of the owner | one share of `SCREENER_CACHE_BYTES`, LRU; the presets pinned | `run.ts:133-134`, `server.ts:99-124` |
| Counts cache | (snapshot, definition hash) | 50,000 entries (`COUNTS_KEEP`), LRU; the presets pinned | `server.ts:130-151` |
| Series LRU (custom parameters) and the pinned tails | `seriesKey` (`metrics.ts:201`) per ticker | one share of `SCREENER_CACHE_BYTES` per compute thread; pinned tails not counted | `metrics.ts:208` `SeriesCache`, `snapshot.ts:418-434` |
| One request's views | ticker | `CALC_KEEP` 256 tickers hold a `Calc` (released on eviction) | `run.ts:217`, `:226-266` |
| Disk cache of the files | sha256 | `SCREENER_CACHE_DIR_BYTES` in `SCREENER_CACHE_DIR` (the container's disk, no volume) | `TerminalClient` `DiskCache` |
| Catalog and universe documents | the publication and its outcome | one each | `apps/screener-worker/src/catalog.ts:89-116` (JSON, gzip level 9, `ETag` = sha256 of the JSON bytes) |

`SCREENER_CACHE_BYTES` is split K + 1 ways (`config.ts:130` `cacheShare`). Every cache is dropped with its snapshot.
Two owners with one definition share one computation byte for byte (test `tests/server.test.ts` "the result cache: two
owners with one definition share one computation, byte for byte"). An answer computed before an advance is sent to its
caller but never cached under the newer publication (`server.ts:401-404`, `:471-478`; semantic review S4; test
`tests/refresh.test.ts` "a screen still computing when the same files advance the publication is never cached under the
newer one").

**Pinning** (`server.ts:372-381` `pinned`): `data_version` pins run, counts and preview to the current snapshot, or to
the previous one during `SCREENER_PREVIOUS_GRACE_S`; an older version answers `409 DATA_VERSION_CHANGED`; one this
replica has not loaded while terminal-api names a newer publication answers `409 DATA_VERSION_PENDING` (edge-bff
retries it once). Test: `tests/refresh.test.ts` "versions: a run pinned to the previous snapshot is served in the grace
window and refused after it ...".

### 1.7.8 Private API and logs

Header `x-screener-worker-key` (at least 32 characters, compared in constant time, `server.ts:154-158`) on every route
except `/health` and `/ready`; `x-screener-owner` (16 hex: the first 16 of HMAC-SHA256(`SCREENER_WORKER_KEY`,
`owner_key`) computed by edge-bff) selects the owner's lane and budget (`server.ts:416-421`). Routes (`server.ts` header
`:5-16`, `contract.ts:544` `WORKER_ROUTES`): `GET /health` (versions, `published_at`, `snapshot_age_seconds`, refresh
state), `GET /ready` (200 only with a loaded snapshot, else 503 `SCREENER_NOT_READY` with `Retry-After`: the Railway
healthcheck), `GET /v1/catalog` and `/v1/universe` (`ETag`, `304`), `POST /v1/run`, `/v1/preview`, `/v1/counts` (gzip
with `ETag`), `POST /v1/validate` (`{valid, definition_hash, normalized, versions}`; `versions` is additive,
`contract.ts` `ValidateResponse`). Every computed answer opens with `versions` and `data`, so edge-bff reads
`price_data` and `published_at` from the first bytes of a gzip answer. The rules it promises edge-bff are in
`apps/screener-worker/CONTRACT.md`.

Logs are one JSON object per line with no key, header, body or presigned URL (test `tests/server.test.ts` "logs explain
a request ... no key or URL in any line"): `start` (configuration without secrets, versions), one `refresh` line per
publication (data version, files, bytes, granted and cached files, per-phase ms, pinned series, `snapshot_digest`,
rss), `swap`, `REFRESH_FAILED` with its code, and one `run`, `preview` or `counts` line per request (owner tag,
`definition_hash`, cache hit, predicted ms, stages with tickers in and out, conditions with their source, pinned and
LRU hits, series computed, queue, busy and total ms, payload bytes, status). The full event list is in the worker
README "Logs".

## 1.8 Stage 5: edge-bff (BRANCH)

`apps/edge-bff/app/screener.py` (`Screeners`, `:598`), mounted like the Backtest module (`apps/edge-bff/app/main.py:436`
`screeners.routes`):

| Route under `/api/v1/screener/` | Auth | Worker route |
|---|---|---|
| `GET catalog`, `GET universe` | session | `GET /v1/catalog`, `/v1/universe` |
| `POST run`, `preview`, `validate`, `counts` | session + `Origin` + `X-CSRF-Token` | the same under `/v1/` |
| `GET items?kind=screen\|metric`, `PUT items/{item_id}`, `DELETE items/{item_id}` | session; writes with CSRF | `PUT` validates through `/v1/validate` first |
| `GET watchlist`, `PUT watchlist/{ticker}`, `DELETE watchlist/{ticker}` | session; writes with CSRF | — |

- **Relay as bytes.** `run`, `preview` and `counts` are passed through as the worker's gzip bytes with its `ETag`
  (`validate` as the worker's JSON); edge-bff reads only the first 4,096 inflated bytes for `price_data` and
  `published_at` (`PEEK_BYTES`, `screener.py:59`) and parses only error bodies (and a validation's hash and versions
  for a saved item). Test `test_relayed_answers_are_the_workers_gzip_bytes_never_parsed`.
- **Refusals.** The worker's contract refusals are relayed at their status (`RELAYED`, `screener.py:51`); any other
  4xx is `503 SCREENER_UNAVAILABLE` (test `test_worker_refusals_outside_the_contract_are_unavailable`); a
  `DATA_VERSION_PENDING` is asked once more on a new connection, then `503 SCREENER_NOT_READY` with `Retry-After` 2
  (`PENDING_RETRY_SECONDS`, `:54`).
- **Catalog and universe** are kept in memory per worker state (versions and refresh, read from `/health` at most every
  60 s, `HEALTH_SECONDS`, `:69`), dropped at once when any answer names a newer publication, and never go back to an
  older one; `ETag` and `304` (tests `test_catalog_and_universe_are_kept_per_worker_state_with_an_etag`,
  `test_a_newer_publication_seen_in_a_run_drops_the_cached_catalog_at_once`,
  `test_the_catalog_never_goes_back_and_ignores_transient_refresh_states`). edge-bff adds its own limits to the
  catalog's `limits[]` (`own_limits`, `:531-562`: `saved_items` 50 per kind, `watchlist` 500,
  `saved_definition_bytes` 65,536, `request_bytes` 131,072, `inflight_per_page` 1).
- **Latest wins** per (owner, page) through `client_order {page, seq}` (`latest`, `:777`); an older call answers 409
  `SCREEN_REPLACED` or `PREVIEW_REPLACED`; a caller that left is stopped at the worker.
- **Saved items** are validated by the worker before they are stored, with the `registry` and `screener_registry` of the
  same answer (`validated`, `:845-867`; `/health` versions when an answer has none), and validated again on load when
  they were saved under other versions ("needs review" with the field; nothing adjusted). Every store statement filters
  `owner_key`.
- **Settings** (`apps/edge-bff/app/config.py:113-122`): `SCREENER_WORKER_URL` and `SCREENER_WORKER_KEY` together or not
  at all (empty = off, `503 SCREENER_DISABLED`), the key at least 32 characters, the host
  `screener-worker.railway.internal` over http outside `local`, and `SCREENER_TIMEOUT_SECONDS` in (0, 3600] = the
  worker's `SCREENER_DEADLINE_MS` / 1000. The saved-item limits are constants (`SCREEN_LIMIT` 50, `WATCHLIST_LIMIT`
  500, `screener.py:76-77`).
- **Page and frame**: `/screener` (`main.py:306`) and `/screener-app/` with its assets (`main.py:384-392`) under
  `SCREENER_CSP` (`main.py:55-58`: `connect-src 'self'`).
- **A new metric needs no edge-bff change:** the catalog is relayed as the worker built it.

Tests: `apps/edge-bff/tests/test_screener.py` (35 tests, on a disposable PostgreSQL through `EDGE_TEST_POSTGRES_URL`;
one browser test with Chromium).

## 1.9 Stage 6: the page and its load sequence (BRANCH)

A port of the user's prototype (`screener EDGE layout.html`), module by module, under `apps/edge-bff/screener/src/`.
Words of the app live in `src/texts.ts`; words of the EDGE shell in `apps/edge-bff/static/edge-labels.js` (AGENTS.md).
The page holds no formula code and downloads no rack file (test `tests/bundle/bundle.test.mjs`); its CSP is
`connect-src 'self'`.

Load sequence (`src/app.ts` header `:1-14`; PAGE LOAD SEQUENCE 6c.4; the Terminal and Backtest pattern):

| Step | What happens |
|---|---|
| S1 | the frame's static markup is the first paint, each data area with the shared loading ring (`apps/edge-bff/terminal/src/ui/spin.ts`) |
| S2 | `boot()` sends at once: session, catalog and universe (with `If-None-Match` from the boot pointer), saved screens, My metrics, watchlist |
| S3 | after an authenticated answer, the cached catalog, universe and last result are drawn from the browser's file cache when the pointer names them for this login, marked "Updating…" (`src/api/boot-cache.ts`: IndexedDB `terminal-files` through the Terminal's `rack.ts` `fileCache`, keyed by sha256 = the `ETag`; pointer `localStorage` `scr.boot`; a result only at versions equal to the cached catalog's) |
| S4 | `304` confirms them; `200` replaces them (stored only when the bytes hash to the `ETag`) |
| S5 | an empty screen needs no run (its rows are the universe after `universe.ts`, the function the worker runs in S0); a remembered screen whose cached result has the current versions needs no run either; otherwise `POST run` |
| S6-S8 | saved screens and the watchlist fill in when they answer; preview, "Stock vs IHSG", counts and CSV wait until asked; edits are debounced (`src/run.ts`) |

Tests: `tests/page/page.test.ts` ("boot pointer", "live client", "results sort", "universe view and chips", "remarks"),
`tests/page/forms.test.ts`, `tests/page/refusals.test.ts` (every refusal worded from the catalog's `limits[]` entry:
place, rule, what this one needs, the fix; nothing kept in the page), the Chromium smoke `tests/smoke/smoke.mjs`.
Targets (P28, PROPOSED on dev): frame first paint ≤ 1.4 s cold, first results of an empty screen ≤ 1.8 s cold, no
main-thread task over 50 ms; locally no page task went over 50 ms (LOCAL); `verification/screener/page_timing_dev.py`
measures them on dev after the deploy.

**Disabled with a reason.** A metric whose availability is not `AVAILABLE` is shown, disabled, with the reason the
catalog gives (`REQUIRES_DATA`, `REQUIRES_DECISION`, `NOT_APPLICABLE`). A preset is enabled only when all its legs are
available; it never runs with a leg removed.

## 1.10 The indicator contract

```
 workbook Technical_Indicators_53_Frontend_Display_Spec.xlsx (user upload, not committed)
        │ hand-kept copy
        ▼
 apps/edge-bff/terminal/src/data/indRegistry.json  (53 rows: id, key, name, short, req, outs, params, def/min/max/opts)
 apps/edge-bff/terminal/src/calc/indicators.ts      (F: the formulas, line 277; DEFAULTS: the defaults, line 215)
        │ apps/backtest-worker/scripts/build-registry.mjs   (npm run registry / registry:check)
        ▼
 apps/edge-bff/backtest/src/core/backtest-registry.json
        │   registry_version = sha256(indRegistry.json + indicators.ts)[:16]
        │ + apps/edge-bff/screener/src/core/screener-overlay.json (hand-kept product choices)
        │ + fields derived by probes that run F on deterministic series
        │ + the parity oracle from `python3 scripts/terminal_indicator_spec.py --json`
        │ apps/edge-bff/screener/scripts/build-screener-registry.mjs                    BRANCH
        │   (npm run registry / npm run registry:check, in apps/edge-bff/screener)
        ▼
 apps/edge-bff/screener/src/core/screener-registry.json   screener_registry_version        BRANCH
        │ served through GET /v1/catalog (registry.ts catalogIndicators, caps at SCREENER_CAP_BUDGET_MS)
        ▼
 the page's builder (no XPARAM copy in the page)
```

- **FACT.** `build-registry.mjs` accepts a parameter only when `DEFAULTS` has it, takes the module's default, and
  records the others under `not_accepted` with a reason; it throws when a registry row has no function in `F` or
  `DEFAULTS` has a key the registry lacks. `npm run registry:check` fails on a stale file; the backtest worker exits at
  start when the artifact does not match its sources (`apps/backtest-worker/src/server.ts:403`).
- **The approved formula contract (FACT, user 2026-10-25).** "Yang ada kita sesuaikan saja dengan feature 4, tapi jika
  tidak ada kita pakai HTML": an indicator Feature 04 stores follows Feature 04 (TA-Lib seeds); the others follow the
  Terminal reference engine. Verified in `apps/edge-bff/terminal/tests/calc/PARITY.md`.
  `scripts/terminal_indicator_spec.py` holds the specification of every indicator and generates
  `verification/terminal_api/INDICATOR_SPEC.md` and the applied migration `20261025_102_terminal_indicator_formulas.sql`
  (the AI's `AI_formula_reference` rows CALC_201 onward); its `--check` proves both unchanged.
- **The screener registry (BRANCH; the generator's header comment).** The overlay holds only
  product choices, per indicator: `shape`, the allowed test forms per output with the prototype's operators and labels,
  search `synonyms`, a one-line `description` in our own plain English (20-160 characters, checked by
  `overlayProblems`), the `default_test` a new card opens with, the options of an enum a user decision narrows (P17 a:
  I43 anchors); plus explicit `overrides` with their evidence (one: I09 `factor` exclusive minimum, ERRORS M257) and the
  provisional `cost_model` of the caps (P5: 5.96 ns per bar per length unit, from one CCI(1000) run). The generator
  derives, by running `F`: `first_valid_bar` per output; `history_class` (window, recursive, cumulative, calendar) by a
  cut probe; unit and `level_comparable` by scaling and shift probes; `price_compare_lag` by a lag probe; `inputs` per
  enum option by a poison probe; narrowing (an exclusive minimum where the output degenerates; integer-only where `F`
  floors; `not_accepted` parameters hidden); `cost_class` by counting the work F does at two lengths with V8 block
  coverage, never by timing, so the file is the same bytes at any machine load; caps; the Feature 04 / Feature 01 oracle
  mapping from `scripts/terminal_indicator_spec.py --json`. `screener_registry_version` is the first 16 hex of the
  sha256 of the generated document without that field (read it from the file: it moved with each generator change on
  2026-10-29, while the cost probe was made reproducible), so any input or derived change moves it.
- **Narrow-only.** The overlay and the derived narrowing may only narrow the base registry
  (`registry.ts:87` `registryProblems` fails on a wider range), so every transferable screener condition is also valid
  for the Backtest.
- **Checks.** `npm run registry:check` re-derives every field and fails on a difference
  (`tests/core/registry-check.test.mjs`); the cost probe's rule is tested in `tests/core/registry-cost.test.mjs`; the
  overlay has one entry per base id and vice versa (`tests/core/registry.test.ts` "has one entry per base id and vice
  versa"); every parameter of the 53 is accepted and refused at the same edges by the catalog the page reads and by
  validation (`tests/core/params.test.ts`); the worker refuses to start on a stale registry (section 1.7.1).

## 1.11 The non-indicator metric catalog and derived availability (BRANCH)

Everything that is not one of the registry indicators is described as **data** in
`apps/edge-bff/screener/src/core/screener-metrics.json`: 10 transforms (`fn`, label, `args` with ranges, `ref_args`,
`tests`, `formula`, `interpretation`, `misuse`, `evidence`), 75 metrics (11 patterns, 4 transform-based metrics such as
the 52-week high distance, the `return_rank` cross-section, 4 universe attributes, the 20 flow metrics FL01-FL20 of
PHASE 2, the 32 fundamentals of APPENDIX C.3 with the 2 dividend metrics among them, index membership, listing board,
notation) and the `periods` block (1M, 3M, 6M, 1Y = 21, 63, 126, 252 sessions, P23 a).
`apps/edge-bff/screener/src/core/catalog.ts:75` `METRICS_CATALOG` loads and checks it at import, and `catalogProblems`
again at the worker's start. Each metric entry carries:

| Field | Meaning |
|---|---|
| `id`, `group`, `kind`, `label`, `short`, `synonyms` | identity and the page's words; `kind` is one of the wire kinds of section 1.7.4; a fundamental is `kind: 'universe'` with a fundamental `group` |
| `params` | each with type, label, default, min, max, `exclusive_min`, `integer`, `step` or `options` |
| `tests` | the test kinds it allows (`value`, `state`, `event`) |
| `unit` | raw unit on the wire (IDR, percent, fraction, sessions, …) |
| `requires {file, columns}` | the xsection file and columns it needs; null when the snapshot already has what it reads |
| `decision` | a sentence naming an open user decision, or null |
| `applies_to` | a predicate over universe attributes (for example `Industry = Banks`); outside it the cell is `NOT_APPLICABLE` (`catalog.ts:142` `appliesTo`) |
| `formula`, `interpretation`, `misuse`, `evidence` | the `Feature_Catalog` fields, so a later AI onboarding can reuse them |
| `unavailable_reason`, `default_test`, `ref`, `fl` | the reason shown while it is unavailable; the card it opens with; a reference template; the FLOW INDICATOR PROPOSALS id |

The page shows `label`, `short`, `interpretation`, the parameter labels and options, `misuse`, `decision` and
`unavailable_reason` as they are (with the availability sentence `availabilityOf` adds), so they are plain English:
name another metric or indicator by the label the page shows ("Bandar balance", "Relative Volume"), never by its id,
and carry no decision, flow, plan or registry id (P11, FL09, EXEC-MCAP, I37), code (`INSUFFICIENT_HISTORY`), wire or
column name (`market_board`, `asOf`). `formula` and `evidence` are not shown and may use them. Test:
`apps/edge-bff/screener/tests/page/plain-words.test.ts` walks every user-visible string of the catalog with the
pattern of `tests/page/plain-words.ts` and fails naming the field.

**Availability is derived at run time** (`validate.ts:52-61` `availabilityOf`): `REQUIRES_DECISION` when `decision` is
set; `REQUIRES_DATA` when `requires.file` is not in the publication's `state.json` xsection index; else `AVAILABLE`.
Columns are checked only against an index entry that lists them, and the entries terminal-api serves carry no column
list, so today only the file name is checked. `NOT_APPLICABLE` is per ticker, from `applies_to`. The worker takes the
map at each swap (`apps/screener-worker/src/server.ts:278`, `apps/screener-worker/src/catalog.ts:28-29`
`metricAvailability`), not at a skip-unchanged advance. Test: `tests/core/catalog.test.ts` "derives availability from
the published index: flow needs its files, technical metrics need none, a decision wins". Nothing is enumerated in the
page or in validation code.

**Availability is not capability.** "AVAILABLE" says the file is published; it does not say the worker reads it. The
worker reads only `PHASE1_FILES` (`snapshot.ts:56`), and a flow reference is refused at bind
(`condition.ts:182`, `422 METRIC_UNAVAILABLE`) whatever the catalog says. A file indexed before the worker can read it
would therefore show its metrics enabled while every run with them is refused (OPEN; the deploy order in 2.3 L12 avoids
it). Consequence for onboarding: **a new metric of an existing kind over a file the worker already reads needs only
catalog entries; a new file needs worker code (its name in the file list, a decoder, its data version, its binding)**
(section 2.1).

**Presets** (`presets.json`, 26 presets of APPENDIX A.2; `apps/edge-bff/screener/src/core/catalog.ts:76` `PRESETS`):
each `{id, category, name, why, definition}` and for eight of them the prototype's default sort (`view.sort`). A preset
is `AVAILABLE` only when every enabled leg and metric filter is (`validate.ts:470-498` `presetAvailability`; it never
runs with a leg removed); the available ones are computed at each swap and kept pinned in the result cache, so a preset
click is a cache hit. Phase 1 publications make the technical presets available. Test: `tests/core/catalog.test.ts`
"holds the 26 presets of APPENDIX A.2; the technical ones are available on a Phase 1 publication, the others name their
legs".

## 1.12 Feature 04's role and the parity checks

DECIDED (P2 a, 2026-10-28): Feature 04 is unchanged (no column, version, checkpoint, worker or migration change) and is
not read at run time. It keeps three roles:

1. **Parity oracle in tests (BRANCH, recorded).** `scripts/screener/parity_f04.py` (with `parity_f04_core.mjs`)
   computes with the screener core on the final daily price rows read read-only through pgweb, and compares on every
   equity ticker at the latest common date: the snapshot path (registry-default columns `sma_20`, the three MACD
   columns, `rsi_14`, the three Bollinger columns, `atr_14`, `adx_14`, and the derived %B, bandwidth, NATR, stddev and
   PPO line) and the dynamic path (`sma_50`, `ema_12`, `ema_26`, `ema_50`, `ema_200` through an empty cache), relative
   difference ≤ 1e-12 with identical nulls; Feature 01 for I35, I37 and I17 within 1e-9; I33 asserted different (sample
   vs population stdev); a perturbed BBCA self-check must fail. The mapping is the generated registry's
   `indicators[].oracle`, from `scripts/terminal_indicator_spec.py --json`. Record:
   `verification/screener/F04_PARITY.md`, **PASS** at 2026-10-28 (825 tickers; run 2026-10-29 02:20 UTC; registry
   `b6a8dc0ba206ed65`). Its own rule asks for a re-run when `registry_version` or the Feature 04 calculation version
   changes; the record names `screener_registry_version` `0bc46ac2a39d7c21`, older than the working tree's (the
   cost-probe change moved it; no formula changed).
2. **Optional reconciliation file** (PHASE 2, needs a SELECT grant on Feature 04 in migration 2).
3. **AI consumer**, unchanged.

Why not a run-time source (report 6.6): no precision gain, 9 of 53 indicators fully covered, a second time base (Feature
04 finishes at about 10:09 UTC, the rack at about 13:03 UTC), coupling to its repair state, and no grant.

Other parity and oracle checks every change must keep green (BRANCH):

| Check | What it proves |
|---|---|
| `tests/core/evaluate.test.ts` "parity with the backtest core (conditionSeries[at]) on 200 tickers" | the screener's STATE and EVENT equal the Backtest's own condition series |
| `apps/screener-worker/tests/run.test.ts` | VALUE, STATE, EVENT, ALL / ANY / AT LEAST and pruning equal F and the backtest core's `compare` directly |
| `tests/core/oracle.test.ts` | random whole screens (240 seeds in the suite; 3,000 by hand with `ORACLE_SEEDS=3000`) equal an independent brute-force reading of the rules, cold and pre-warmed, pruned and exhaustive |
| `apps/screener-worker/tests/typed_views.test.ts`, `snapshot.test.ts` | F is bit-identical on the shared columns; every pinned tail equals the dynamic `series()` |
| `tests/core/asof.test.ts`, `tests/core/lookback.test.ts` | no look-ahead on any path; pattern windows and remark edges exact |
| local end-to-end (scratch, not committed; 109 of 109 checks) | the real publisher → the real terminal-api app → the real worker process on the full history, against an independent oracle, including P4, versions, preview and counts |

## 1.13 Versions

| Version | What it hashes | Changes when | Where it shows |
|---|---|---|---|
| `price_data` | `dataVersion` (`datafile.ts:271`) over (ticker, `price`, pack sha256) of every ticker of the price file (`snapshot.ts:253`) | a publication changes any price | every answer `versions`; `data_version` pinning |
| `flow_data` | the same over the flow files | PHASE 2 (null now, `snapshot.ts:254`) | every answer |
| `registry` | `registry_version` of `backtest-registry.json`, passed through | `indRegistry.json` or `indicators.ts` changes (a registry release) | every answer; saved items |
| `screener_registry` | sha256 of the generated `screener-registry.json` without the field (`apps/edge-bff/screener/src/core/registry.ts:78`) | the overlay, the base, the generator or a probe result changes | every answer; saved items |
| `screener_engine` | the first 16 hex of the sha256 over `<path> \t <sha256>` of the screener core (`.ts`, `.json`), the worker's `src`, the backtest core, the Terminal's calc module and `apps/backtest-worker/src/terminal.ts`, plus the Node major (`apps/screener-worker/src/version.ts:28-50`) | any of that code changes | every answer; cache keys |
| `definition_hash` | sha256 of the canonical JSON of the normalized definition, parameters resolved, labels removed (`validate.ts:461` `definitionHash`) | the screen changes | run and counts; result cache; saved items |
| `sid` (internal) | price_data + the actions contents + the reference hash (`snapshot.ts:257`) | any of the three changes | every cache key |
| `snapshot_digest` (log only) | the pinned series keys, tickers and tails (`snapshot.ts:386-392`) | any pinned value changes | the `refresh` line; equal across replicas |
| Backtest `engine_version` | every file of `backtest/src/core` and `apps/backtest-worker/src` | **must not change during the Screener build** except as `backtest_worker_baseline.json` records (tripwire) | Backtest results |

A saved screen whose parameter left the registry range after a release is shown "needs review" with the field; nothing
is adjusted (API CONTRACT 8.7; edge-bff test
`test_an_item_saved_under_other_registry_versions_is_validated_again_on_load`). A new data family adds its own data
version beside `price_data` (as `flow_data` will).

## 1.14 Caches, end to end

| Where | What | Key | Lifetime |
|---|---|---|---|
| terminal-api process | manifests, the state | ticker; `finished_at` | until the next publication (checked every 60 s) |
| Worker memory | snapshot: bars, pinned tails, universe rows, remarks | `sid` | until the swap after the next publication, plus `SCREENER_PREVIOUS_GRACE_S` for pinned requests |
| Worker memory | series LRU, result cache, counts cache, per-thread views and cross-sections | section 1.7.7 | dropped with their snapshot |
| Worker disk | verified gzip files | sha256 | LRU in `SCREENER_CACHE_DIR` (no volume) |
| edge-bff memory | catalog and universe bytes and their `ETag` | the worker's versions and refresh state | a newer state on `/health` or a newer publication in any answer |
| Browser IndexedDB `terminal-files` | last catalog, universe and result bytes | sha256 (= `ETag`), pointer `localStorage` `scr.boot` per login | shared 50 MB LRU (`rack.ts` `CACHE_LIMIT`) |
| `edge_bff` tables | saved items, watchlist | `owner_key` | never cached |

Every byte cache is keyed by content or by version, so a new publication never serves stale numbers.

## 1.15 Limits (provisional, P5; replaced by the Phase 17 measurements)

Every worker limit is an environment variable **with no default**: the service does not start without it (backtest
worker convention; `apps/screener-worker/src/config.ts`). Each limit is published in the catalog's `limits[]` with its
rule, one right and one wrong example generated from the value (`apps/screener-worker/src/catalog.ts:46-85`
`limitEntries`; AGENTS.md "Gates and evidence"), and the page words every refusal from that entry. The proposed dev
values below are LOCAL (`BENCHMARK_LOCAL.md` section 8) unless marked; the worker README "Configuration" has every
variable.

| Limit | Proposed dev value | Variable |
|---|---|---|
| Active conditions | 20 | `SCREENER_MAX_CONDITIONS` |
| Universe metric filters | 8 | `SCREENER_MAX_METRIC_FILTERS` |
| `within` (technical) | 130 sessions; the snapshot tail is this + 1 | `SCREENER_WITHIN_MAX` |
| Indicator lengths | derived cap per O(N·n) parameter: 567 at 4,500 ms | `SCREENER_CAP_BUDGET_MS` (4500) |
| Compute budget, deadline | 4,500 ms predicted; 20 s from arrival | `SCREENER_MAX_CPU_MS`, `SCREENER_DEADLINE_MS` (edge-bff `SCREENER_TIMEOUT_SECONDS` 20) |
| Per-owner compute (P33) | 30,000 thread ms per minute | `SCREENER_OWNER_CPU_MS` |
| Owner lane, queue | 1 running per owner (K - 1 at K = 2); 4 waiting per replica | `SCREENER_OWNER_INFLIGHT`, `SCREENER_QUEUE` |
| Counts request | 50 definitions | `SCREENER_MAX_COUNTS` |
| Response, request | 4,194,304 bytes of JSON; 131,072 bytes of body | `SCREENER_MAX_RESPONSE_BYTES`, `SCREENER_MAX_REQUEST_BYTES` |
| One xsection file (gzip), inflated, one refresh | 2 × the measured size: 24,000,000 / 150,000,000 / 24,000,000 locally; re-derived from the first dev publisher run | `SCREENER_MAX_FILE_BYTES`, `SCREENER_MAX_INFLATED_BYTES`, `SCREENER_MAX_REFRESH_BYTES` |
| Threads, heap, caches, memory | K = 2, 512 MB per thread, 256 MiB of caches, a 2.75 GB replica | `SCREENER_THREADS`, `SCREENER_THREAD_HEAP_MB`, `SCREENER_CACHE_BYTES`, Railway memory limit |
| Saved items, watchlist (edge-bff constants) | 50 saved screens and 50 My metrics per owner; 500 tickers | `SCREEN_LIMIT` (`screener.py:76`), `WATCHLIST_LIMIT` (`:77`) |
| terminal-api default quota (one shared gateway subscriber) | `files_per_hour` 60, `megabytes_per_day` 300 (`database/migrations/20261025_100_create_terminal_schema.sql:79-83`); overridden to 1e9 on dev, TEMPORARY (decision U1); a service key has its own hourly ceilings instead (EXEC-MU-RUNTIME T1, `BACKTEST_END_TO_END.md` 6.1) | `terminal.quota` |

**Onboarding consequence:** a new file must fit `SCREENER_MAX_FILE_BYTES`, `SCREENER_MAX_INFLATED_BYTES` and
`SCREENER_MAX_REFRESH_BYTES` (raise them by 2 × its measured size), the replica's memory, and the gateway's or the
service account's budget (section 2.3, L2 and L5).

## 1.16 Multi-user notes

The user's requirement (2026-10-28): "ini nanti akan multiuser, jadi infrastruktur harus bisa di scale UP + efficient
cost wise", and (P29) EDGE users are external on every tab. As built (BRANCH):

- **Shared, once per publication:** bars, the pinned series, universe rows, ranks, preset counts and results, catalog
  and universe bytes. A run answer is a function of (publication, versions, definition) only and carries no owner, so
  two users with the same screen share one computation (section 1.7.7).
- **Per user:** session, saved items, watchlist (all keyed by `owner_key`), one run and one preview in flight per page,
  the owner's lane and compute budget in the worker (P33), keyed by an opaque owner tag the worker cannot reverse.
- **Replicas are stateless and their caches per replica (P34).** A replica's whole state is a function of the
  publication and the engine version; any replica can answer any request. Capacity grows by compute threads first (one
  copy of the bars), then replicas (P32: one on dev now, two once external users start). Version skew across replicas
  is handled by pinning, the grace window and `DATA_VERSION_PENDING` (section 1.7.7).
- **Memory (LOCAL, K = 2):** 0.57 GB idle after the start, 1.46 GB at the peak of a refresh with both snapshots alive,
  1.81 GB with 512 MiB of caches full and the previous snapshot in its grace; hence the proposed 2.75 GB limit
  (`BENCHMARK_LOCAL.md` sections 4 and 8). The report's inference was 0.4-0.7 GB steady.
- **terminal-api traffic does not grow with users**: per replica and publication, one grant for at most the two Phase 1
  files (none when the disk cache holds them), about 12 MB.
- **Onboarding consequence:** a new dataset adds to every replica's memory and start time. Measure the inflated size,
  the refresh line's `defaults_ms` and `rss`, and record them (section 2.3, L5).

## 1.17 Send to Backtest (PHASE 1b, PROPOSED, not built)

`apps/edge-bff/screener/src/core/to-backtest.ts` (absent today) translates a screen into Backtest cards with an explicit
lossless or lossy classification, using the Backtest catalog's own `limits` (`max_portfolio_tickers`, `window_bars`,
`max_conditions`). Lossless: registry-indicator conditions `gt`, `lt`, crosses (same instance), Supertrend/PSAR
direction, core patterns, Donchian prior band as `breakout`, all-board `fnet`, `broker`, `top5` (`conditions.ts`
`FLOW`), and ADV as `min_avg_value_20d_idr`. Everything else goes to `left_out` with a reason and travels in the
handoff's full `definition`, so a later Backtest release can adopt it. The handoff is a one-shot
`sessionStorage['edge-backtest-import']` plus a `postMessage` navigation; the Backtest change is page-only (`app.ts`,
new `import.ts`). Decision P13 is open before Phase 1b.

## 1.18 Security

Never in the browser: database URLs, bucket credentials, `TERMINAL_PROXY_KEY`, `SCREENER_WORKER_KEY`, internal hosts.
`/state` and `/xsection` are outside the browser allow-list; `/xsection` accepts only the screener-worker's service key
or the gateway key (section 1.6). The worker holds no database or bucket credential; it compares its key in constant
time and never logs a key, header, body or presigned URL (section 1.7.8). edge-bff filters every store statement by
`owner_key` and puts every write behind the CSRF dependency (test
`test_session_origin_and_csrf_are_required_and_every_write_route_checks_them`).

## 1.19 Operations

- **Environment:** one Railway environment, `dev`. No deploy, manual run or end-to-end inside 00:00-01:45 or
  12:00-13:20 UTC (the publisher's runs, ERRORS M250; measured run lengths), nor 10:00-10:30 and 22:45-23:30 UTC for a
  publisher run (the price crons). A publication torn by a session loaded during the run is refused by the worker
  (section 1.7.3). Claim a deployment only at the exact deployment's `SUCCESS` (AGENTS.md).
- **Deploy sources:** screener-worker and edge-bff from GitHub `main` (after each merge check that the merge commit was
  deployed, ERRORS M252); terminal-api and terminal-publisher by CLI upload under the ERRORS M248 procedure (merge
  first, deploy the merge commit; the last upload wins); a manual publisher run follows ERRORS M229 (clear the cron,
  `railway up`, restore). The worker's `/ready` is its Railway healthcheck, so its deployment reaches `SUCCESS` only
  with a snapshot loaded.
- **New Railway resources** (the screener-worker service) are created through a pinned, reviewed IaC plan
  (`railway config plan --out`, apply only when the plan holds exactly the intended changes; every variable of the
  service listed as `preserve()`; ERRORS R29, R41, R42; report 6.17).
- **Tests per part** (one suite at a time):

  | Part | Command (from the folder) | Status |
  |---|---|---|
  | publisher | `python -m pytest apps/terminal-publisher/tests` | FACT; xsection tests BRANCH |
  | terminal-api | `python -m pytest -q` in `apps/terminal-api` | FACT; `test_xsection_*` BRANCH |
  | Terminal formulas | `npx vitest run tests/calc` in `apps/edge-bff/terminal` | FACT |
  | backtest worker | `npm test`, `npm run registry:check` in `apps/backtest-worker` | FACT |
  | indicator spec | `python3 scripts/terminal_indicator_spec.py --check` | FACT |
  | screener registry | `npm run registry:check` in `apps/edge-bff/screener` (needs python3 for the oracle) | BRANCH |
  | screener core and page | `npm run typecheck`, `npm test` (vitest; the bundle tests need `npm run build` first) in `apps/edge-bff/screener`; Chromium smoke `tests/smoke/smoke.mjs` | BRANCH |
  | screener-worker | `npm test` in `apps/screener-worker` (61 of 61 on 2026-10-29, with this document's pointer check) | BRANCH |
  | edge-bff | `EDGE_TEST_POSTGRES_URL=<disposable Postgres> python -m pytest -q tests/test_screener.py` in `apps/edge-bff` | BRANCH |
  | tripwire | `npm run tripwire` in `apps/edge-bff/screener` (`scripts/screener/check_backtest_untouched.mjs`; its tests: `node --test scripts/screener/check_backtest_untouched.test.mjs`) | BRANCH |
  | Feature 04 parity | `python3 -I scripts/screener/parity_f04.py --write` (read-only through pgweb), record in `verification/screener/F04_PARITY.md` | BRANCH, recorded PASS |

## 1.20 Open and temporary items that affect onboarding

| Item | Status | Where |
|---|---|---|
| Mixed adjusted/raw price history; the Screener's price-break remark | OPEN; the remark is TEMPORARY until the data-layer fix | ERRORS D22; report 6.12 |
| Availability says "published", not "the worker reads it": a file indexed before the worker decodes it shows its metrics enabled while runs refuse them | OPEN; avoided by the deploy order (2.3 L12) | section 1.11 |
| The cost model: one provisional constant, a single-value tracker per indicator, an estimate blind to a thread's LRU | OPEN, Phase 17 (fitted `a + b x min(n, bars)` per indicator) | `BENCHMARK_LOCAL.md` section 7 |
| A counts request is one all-or-nothing job on one thread (50 screens with their own custom series took 13-17 s of a 20 s deadline) | OPEN | `BENCHMARK_LOCAL.md` section 9 |
| The refresh pre-warm runs on the builder alone while a snapshot serves (24-29 s, 47-58 s under load) | OPEN; check the 2-minute refresh target on the service | `BENCHMARK_LOCAL.md` sections 2, 9 |
| The workers read reference files without checking an announced sha256 | OPEN (EXEC-MU-RUNTIME T5 readers' side) | `BACKTEST_END_TO_END.md` 6 |
| Broker data lags prices | OPEN | ERRORS M243; P10 |
| No delisted tickers, no historical membership or sector history before 2026-09-28 | no point-in-time screens; history is "today only" | APPENDIX C.6 |
| One shared gateway account with an unlimited quota override; the gateway key still reaches `/xsection` | TEMPORARY | decision U1; EXEC-MU-RUNTIME step "remove the gateway key's `/xsection` access" |
| Registry defects behind the screener narrowing (I09 factor 0, I37 label, Donchian same-bar test, `annualization_periods` floor) | OPEN for the Backtest; TEMPORARY screener-only narrowing until the registry release | ERRORS M255-M258; P6 |
| `topNAccumulation` to be copied into the screener core because `flow.ts` is in the Backtest's engine hash | PHASE 2, PROPOSED; a test is to pin `flow.ts`'s hash | report 6.11 |
| Flow decisions P9 (bandar), P10 (lag), P20 (calendars, default broker), D1-D14 | OPEN, before Phase 2 (P9 before Phase 3) | FLOW INDICATOR PROPOSALS 16.11 |
| Fundamentals, market cap, index membership, board, notation, free float | no data; shown disabled with reasons (P11) | APPENDIX C; EXEC-MCAP waits for its go |
| A saved screen's tooltip shows the save date, not the data date (page O4) | OPEN, no schema change in Phase 1 | BUILD_COMMON page items |

---

# Part 2 — Onboarding a new indicator, metric or dataset

## 2.0 Before you start

1. **Read** this document's Part 1, `ERRORS_AND_SOLUTIONS.md` Part A (and Part C for macro or cross-asset data), and the
   AGENTS.md required reading for any database or Railway work. Before touching the publisher or a terminal-api route
   the Backtest reads, read `BACKTEST_END_TO_END.md` and `apps/edge-bff/backtest/CONTRACT.md` in full (AGENTS.md).
2. **Classify** the new thing with the decision tree (2.1). The class decides which layers change.
3. **Ask the user** what only the user can decide, before any load: the definition and its parameters, the source and
   its licence, the default and the ranges, the as-of rule, what a missing value means, whether the AI should read it
   too. Record the approval with the user's words and date in `PLAN.md` or `EXEC.md` (AGENTS.md "Plans"); approval to
   plan is not a go.
4. **Settle every gap against Part A with the user before loading** (AGENTS.md). Part A is the contract for any new
   table, whether or not the AI reads it.
5. **Inspect the live state first** (read-only), and cite file:line, log or run ID as evidence for every claim
   (AGENTS.md "Gates and evidence").
6. **Do not change protected files as a side effect.** `indicators.ts`, `indRegistry.json`,
   `apps/edge-bff/backtest/src/core/**`, `apps/backtest-worker/**`, `features/feature04/**`, `apps/feature-04-worker/**`
   and `apps/stockbit-updater/**` (the tripwire's `PROTECTED` list) change only in their own approved release (2.4); a
   backtest-worker change also needs its recorded baseline (`scripts/screener/backtest_worker_baseline.json`).

## 2.1 Decision tree by data class

```
 What is the new thing computed from?
 │
 ├─ only one ticker's own daily OHLCV bars ─────────────────────────────── CLASS A: technical
 │     ├─ one of the 53 indicators with other parameters ........ nothing to onboard (custom parameters, dynamic path)
 │     ├─ arithmetic or a pattern over existing outputs or bars ... a transform or pattern: screener-metrics.json entry
 │     │                                                            + code in screener core (screener_engine changes)
 │     └─ a new formula ........................................... a registry release (P6): F + indRegistry.json
 │                                                                  + backtest-registry.json + backtest-worker redeploy
 ├─ broker or investor-type transactions (IDX_Broker_Summary → F05/F02/F03/F06) ── CLASS B: flow
 ├─ company-reported numbers (statements, ratios, dividends, share counts) ──────── CLASS C: fundamental
 ├─ one series not tied to an IDX ticker (FX, a policy rate, a bond yield,
 │  a commodity, a foreign index), compared with or gating the stocks ───────────── CLASS D: macro / cross-asset
 └─ a per-ticker attribute that is not its own trading (index membership,
    listing board, notation, market cap, free float, listing date, instrument type) ─ CLASS E: universe attribute
```

What changes, per class (yes = always; maybe = depends; no = never):

| Layer | A new formula | A transform | B flow | C fundamental | D macro | E universe |
|---|---|---|---|---|---|---|
| L1 PostgreSQL table, grants, catalogs | no | no | maybe (grant, refresh) | yes (new tables) | yes (new or existing table, grant) | yes (new column or history table) |
| L2 publisher xsection file | no (bars already published) | no | yes | yes | yes | yes (a separate file) |
| L3 terminal-api | no | no | no | no | no | no |
| L4 registry / metric catalog / contract | yes (registry) | yes (`screener-metrics.json`) | yes (entries FL01-FL20 exist) | yes (32 entries exist, `kind: 'universe'`) | yes (+ a wire kind the first time) | yes (entries exist for membership, board, notation) |
| L5 screener-worker | regenerate only (the 53 are pre-warmed by a loop) | code in screener core | file list, decoder, binding, metrics | file list, decoder, row field, as-of | file list, decoder, alignment, a new kind | file list, decoder, row field |
| L6 edge-bff | no | no | no | no | no | no |
| L7 page | texts only (generic builder) | texts | texts | texts, "period X, published Y" | texts | texts, filter control |
| L8 Backtest | the same release | optional, later | optional, later | screen only | optional, later | screen only |
| L9 AI exposure | AI formula row | no | optional onboarding | optional onboarding | optional onboarding | optional onboarding |

Notes: "no" for terminal-api rests on `/xsection` validating names against the index (BRANCH, section 1.6); a new
service that reads `/xsection` needs its name in `XSECTION_SERVICES` (`apps/terminal-api/app/main.py:39`). "A wire kind
the first time" means the first macro series needs one new reference kind in `contract.ts` `MetricRef` and in
`catalog.ts:152` `KINDS` (worked example 2.13); a fundamental or a universe attribute is `kind: 'universe'`, read from a
field of the worker's universe row (`condition.ts:152-166`; `apps/edge-bff/screener/src/core/contract.ts:460-462`), so
it needs no new kind (2.14). "File list" means the worker's list of files it reads (today `PHASE1_FILES`,
`apps/screener-worker/src/snapshot.ts:56`): a file outside it is never downloaded, never enters the skip-unchanged rule
or `sid`, and its metrics can never be computed, whatever the catalog's availability says (section 1.11).

## 2.2 What PostgreSQL needs, per class

The user's question: "apa requirementnya di postgres, table apa yang harus disiapkan". Every new table meets
`ERRORS_AND_SOLUTIONS.md` Part A; the table below names what each class needs on top. Names are PROPOSED and settled
with the user.

| Class | Tables to prepare | Key and time | Must carry | Existing pattern to copy |
|---|---|---|---|---|
| A technical | none: bars come from `Price_Stock_Indonesia_IDX` | — | — | — |
| B flow | none new for metrics from F05/F03/F06; a grant through the publisher's read group | `(ticker, trade_date, broker, investor_type, market_board)` (F05) | for trade-count metrics, `buy_freq`/`sell_freq` loaded over the whole window (the loader writes them since 2026-10-25, `apps/stockbit-updater/broker_import.py`, UPDATE_TABLE.md part 0; the history backfill is in ERRORS M200, M201): check their coverage first | migration 2 (report 7.2) |
| C fundamental | a statements table (one row per reported item and version) and a Feature table for derived ratios (TTM, ROE) | `(ticker, fiscal_period_end, period_type, consolidation, item, vintage)`; `available_at` | period type, cumulative or not, currency and scale, filing date, restatement version | `NEW_TABLE_ONBOARDING_PLAN.md` 2.2 (fundamental row), 2.3 (Feature tables) |
| D macro / cross-asset | a price or value table, a universe (series definitions) and a market schedule, with a `_Final` view | `(series, date[, metric][, vintage])`; `release_at` or `market_close_at` + `is_final` | unit and quote convention per series, calendar and time zone, release date, vintage policy | `Price_Fixed_Income` + `Universe_Fixed_income` + `Fixed_Income_Market_Schedule` + view `Price_Fixed_Income_Final` (`DATABASE_CATALOG.md`, fixed income) |
| E universe | a typed column on the universe or an effective-dated history table | `(ticker, valid_from)` bitemporal | effective and recorded periods, availability time, capture basis | `IDX_Stock_Universe_History` (migration `20260927_006_reference_history_point_in_time.sql`; Part A A2.8) |

For every class with a new table, the minimum database work is:

1. **One forward migration** (never edit an applied one; `database/migrations/APPLIED.sha256` and
   `apps/market-ai-orc/tests/test_migrations_frozen.py` enforce it): the table with its key, typed columns, `CHECK`
   lists for fixed categories (A1.4), `ingestion_time` set by the database (A5.21), `COMMENT ON` text with the words a
   user would search for (A4.19), `REVOKE ALL FROM PUBLIC`, exact grants, a `$verify$` block, the rollback as a comment.
   DRYRUN, then APPLY, then read back (`scripts/onboarding/migration_job.py`).
2. **Indexes from measurements, not shape** (AGENTS.md "Performance"; `NEW_TABLE_ONBOARDING_PLAN.md` section 3). For the
   Screener the pattern that matters is the publisher's: "every entity on the newest date or dates" (a cross-section)
   and "every entity over the file's window". Run a bounded `EXPLAIN (ANALYZE, BUFFERS)` with literal date bounds before
   the go, and record it in `DATABASE_CHANGELOG.md`. FACT, why literal bounds: a calendar-CTE join planned a seq scan of
   Feature 06 taking 18.6 s, while per-date reads take milliseconds to seconds (report 6.11; FLOW INDICATOR PROPOSALS
   16.7).
3. **Catalogs** (AGENTS.md step 5; `DATABASE_CATALOG.md` "Mandatory maintenance"): `Table_Catalog` and `Column_Catalog`
   rows for every new public table and column (unit, null rule, definition; never VERIFIED for an inferred meaning);
   `Feature_Catalog` for each derived column (formula, interpretation, recommended use, misuse warning, review status,
   evidence), then `scripts/audit_feature_catalog_semantics.py`; `Feature_Relationship_Catalog` for safe joins; then
   `scripts/sync_database_catalog.py` and `scripts/sync_database_schema.py`.
4. **Read grant for the publisher.** A new group (NOLOGIN) granted to `terminal_publisher_login` only, never to
   `terminal_market_reader` (it also serves the public terminal-api); update `scripts/provision_terminal_logins.py`
   (`MARKET`, `LOGINS`) in the same change, or it rolls back. FACT (live, 2026-10-28): the publisher cannot read
   `Price_Fixed_Income` or `Price_Fixed_Income_Final` today.
5. **Refresh and monitoring:** a loader (an app with a load log), its schedule, who is told when it fails
   (`telegram-monitor` pattern), and how its data reaches the rack: the publisher runs at 07:30 and 19:00 WIB, so a
   source updated after 19:00 WIB reaches the Screener at 07:30 the next day. State it.
6. **Records:** `DATABASE_CHANGELOG.md` (source, rows, range, verification), `DATABASE_SCHEMA.md` (generated),
   `ERRORS_AND_SOLUTIONS.md` for anything found.

## 2.3 The layer-by-layer checklist (every class)

Tick every line or record why it does not apply. "Evidence" is what you cite in the change.

**L1 — Source and PostgreSQL table**

| Check | Evidence |
|---|---|
| Grain and primary key declared; every meaning-bearing dimension in the key (board, investor type, tenor, currency, period type, vintage) (A1.1) | the migration |
| One identifier code system, upper-case and trimmed; a mapping table when codes differ (A1.2) | the migration; a join count |
| Typed time column; the calendar the dates follow; no invented weekend or holiday rows; gaps flagged (A2.5, A2.6) | `time_semantics`; a gap count |
| Reference period vs availability: `release_date` / `available_at` and the vintage policy (A2.7) | columns and catalog text |
| Current-state attributes marked; history effective-dated or captured bitemporally (A2.8) | the history table |
| History depth: all available history; recursive indicators need about 250 observations before the first asked date (A2.9) | min and max dates per entity |
| Numeric columns numeric, each with a unit in raw scale (no "miliar"), percent or fraction declared, sign convention stated (A3.10-A3.13) | `Column_Catalog.unit` |
| Price adjustment basis declared (unadjusted, split-adjusted, total return) (A3.14); for anything combined with IDX prices, the mixed basis of D22 | the catalog text |
| NULL has one meaning; sparse (activity-only) tables declared; identities measured on the full history (A3.15, A3.15a) | the catalog text; a per-year count |
| Idempotent upsert on the natural key, load log, authentication failure stops the load (A5.21, A5.22) | the loader code |
| Disk cost estimated before a derived table is stored; a view where it can be computed when read (A5.25) | the migration header |
| Scheduled (future-dated) rows declared (A5.27) | the catalog text |
| Indexes measured (section 2.2 item 2) | `DATABASE_CHANGELOG.md` |
| Catalog rows and generated documents (section 2.2 item 3) | the migration; `sync_database_catalog.py` output |
| Read grant for the publisher's own group; `provision_terminal_logins.py` updated (section 2.2 item 4) | the `$verify$` result |
| Refresh schedule and monitoring; time to reach the rack stated | the loader; `RAILWAY_CHANGELOG.md` |

**L2 — terminal-publisher (the xsection file)**

| Check | Evidence |
|---|---|
| File name matching terminal-api's `XSECTION_NAME` (`^[a-z0-9][a-z0-9_-]{0,31}$`; section 1.6) and its document: `schema_version`, `dataset` `xsection`, `name`, `units` per column, `means` (what each column and a null mean), `columns`, row order stated (the pattern: `xsection_price_doc`, `xsection_actions_doc`, `publisher.py:404, 425`) | the document builder and its test |
| Its row in the publisher's rebuild table (`XSECTION_REBUILT_BY`, `publisher.py:148`): which modes rebuild it; a failed build keeps the previous entry and the run exits 3 | a test per mode (pattern: `test_modes_that_do_not_rebuild_an_xsection_file_carry_its_entry_forward`) |
| One bounded SQL statement (or one per date with literal bounds) through the read-only login; measured | `EXPLAIN (ANALYZE, BUFFERS)` in `DATABASE_CHANGELOG.md` |
| Deterministic bytes: built with `encode`; values as stored (no rounding, no adjustment); `allow_nan=False` passes | a test: the same rows give the same sha256 |
| Content-addressed key (`indexed_key('xsection')`, `publisher.py:151-157`) and index entry `{key, sha256, bytes, rows, as_of}` in `state.json`, written before `state.json`; `collect_garbage` then covers it with no change | `test_the_xsection_files_are_written_before_the_state_json_that_indexes_them` |
| Change detection: a stamp so `daily` rebuilds the file only when its inputs changed; otherwise the index entry is carried forward | a test: an unchanged source uploads nothing |
| Completeness gate for data written in rounds (a date is published only when it is complete for every ticker) | a fixture with a partial date |
| `as_of` meaning stated (last complete date; for macro the last value available at the cut time) | the document and the catalog entry |
| Verify mode extended: the file against SQL (rows, first and last date, a column sum) in `verify_xsection` (`publisher.py:1145`) | `test_verify_checks_the_xsection_files` and its new case |
| Size: gzip and inflated bytes measured at the first run; fits the worker caps and the daily quota | the `done` log line; `RAILWAY_CHANGELOG.md` |
| Orphans (rows whose ticker is not in the reference file) counted and logged, never named in code | the log line |
| Publisher tests green; backfill then daily uploads nothing new | `python -m pytest apps/terminal-publisher/tests` |

**L3 — terminal-api**

| Check | Evidence |
|---|---|
| No code change needed: `/xsection` validates names against the index (BRANCH, `bucket.py:51` `xsection_index`). Check the entry passes its rules (name, five fields, key pattern) or it is silently dropped from `/state`; and that the total names per publication stay within `MAX_XSECTION_NAMES` (16, `apps/terminal-api/app/main.py:50`) per call. If a change is needed, follow M248 for the CLI deploy and keep `/state`'s existing tests | `apps/terminal-api/tests/test_api.py` `test_xsection_*` |
| Quota: grants per day × bytes fit the screener-worker service account's hourly ceilings (EXEC-MU-RUNTIME T1, `BACKTEST_END_TO_END.md` 6.1) and, while the gateway key is still used, `files_per_hour` and `megabytes_per_day` of the shared subscriber without the TEMPORARY override (6d.7) | arithmetic in the change record |

**L4 — Contract, registry and metric catalog**

| Check | Evidence |
|---|---|
| Indicators (registry release only): base registry regenerated (`npm run registry` in `apps/backtest-worker`), overlay entry (`shape`, the test forms per output with operators and labels, `synonyms`, a one-line `description` of 20-160 characters in our own words, `default_test`), screener registry regenerated (`npm run registry` in `apps/edge-bff/screener`), both `registry:check` green | the generated files; `tests/core/registry.test.ts` "has one entry per base id and vice versa" |
| Other metrics: `screener-metrics.json` entries with the built fields (section 1.11): `id`, `group`, `kind`, `label`, `short`, `params` (ranges; flow maxima derived from the published window), `tests`, `unit`, `requires {file, columns}`, `decision`, `applies_to`, `unavailable_reason`, `formula`, `interpretation`, `misuse`, `evidence`, `default_test` | `catalog.ts:172` `catalogProblems` at import and at the worker's start |
| A new transform `fn` or pattern `type`: its function in `transforms.ts` and its id in `IMPLEMENTED_TRANSFORMS` / `IMPLEMENTED_PATTERNS` (`transforms.ts:152, 334`); an offered pattern without a `decision` must be implemented | `tests/core/catalog.test.ts` "keeps its rules and lists exactly the transforms and patterns transforms.ts computes" |
| A new fundamental: `catalogProblems` holds the count of fundamental entries at 32 (`catalog.ts:199`), so the check changes with the entry (OPEN: a count in code) | `tests/core/catalog.test.ts` "holds the 32 fundamental metrics" |
| Availability derived, never coded: removing the file from a fixture index makes the metric `REQUIRES_DATA` with no code change | `tests/core/catalog.test.ts` "derives availability from the published index: flow needs its files, technical metrics need none, a decision wins" |
| A new wire kind or NA reason added to `contract.ts` only when no existing one fits; each new refusal or NA meets the four "Gates and evidence" items (rule seen first, how to pass, right and wrong example, a message naming the field and the fix) | `contract.ts`; texts |
| Defaults, ranges and thresholds are the user's words, recorded; thresholds never validated against returns are labelled so | `EXEC.md` |
| Presets that use the metric: `presets.json` entries (`{id, category, name, why, definition}`, optional `view.sort`); a preset is enabled only when all its legs are available | `tests/core/catalog.test.ts` "holds the 26 presets of APPENDIX A.2 ..." (the count changes with a new preset) |

**L5 — screener-worker**

| Check | Evidence |
|---|---|
| The file in the worker's file list (today `PHASE1_FILES`, `snapshot.ts:56`): the refresh requires it in the index (`refresh.ts:264-266`), caps it before any grant, grants it only when neither cache holds it, downloads it on the builder with sha256 and size checks and decodes it with the shared decoders (`decodeColumnar`/`inflateVerified`); its sha256 joins the skip-unchanged rule (`refresh.ts:269`) and the snapshot identity `sid` (`snapshot.ts:257`). A file that is optional (Phase 2) needs its own rule: the Phase 1 list makes a missing file fail the refresh | `tests/refresh.test.ts` |
| The metric bound: a new kind or a new source in `condition.ts` (flow is refused at bind until Phase 2, `condition.ts:182`), costed in `run.ts:152-170` `costUnits` or pinned in the snapshot | condition and estimate tests |
| Cross-checks on load (counts, dates, a self-check against a stored oracle where one exists); a failure keeps the previous snapshot and logs `REFRESH_FAILED` | a fixture with a corrupted sha256 |
| Units converted once, at the decoder, from the document's `units`; raw units on the wire | a unit test |
| Alignment: the as-of rule for each cell (own bars, market sessions, or backward as-of on availability) and the `eval_date` each cell reports | a fixture across a holiday |
| Its data version (as `flow_data`) enters `versions` and the cache keys | a version test |
| Memory and start time measured with the new file (the `refresh` line's `rss`, `defaults_ms`, `pinned_series`); the caps (`SCREENER_MAX_FILE_BYTES`, `SCREENER_MAX_INFLATED_BYTES`, `SCREENER_MAX_REFRESH_BYTES`) and the Railway memory limit raised with it | `verification/screener/BENCHMARK_LOCAL.md` locally, `verification/screener/BENCHMARK.md` on dev; the worker README "Configuration" |
| Tripwire green: no Backtest formula or core file changed, the Backtest worker as its recorded baseline approves | `npm run tripwire` (`check_backtest_untouched.mjs`) |

**L6 — edge-bff:** nothing for a new metric (the catalog is relayed). A new route or setting only with its tests in
`apps/edge-bff/tests/test_screener.py`.

**L7 — Page**

| Check | Evidence |
|---|---|
| Labels and reasons worded in `apps/edge-bff/screener/src/texts.ts` from codes and the catalog (a refusal of a limit is worded from its `limits[]` entry, so a new limit needs no page change); shell words in `static/edge-labels.js` | `tests/page/refusals.test.ts`, `tests/page/page.test.ts` |
| Disabled-with-reason states for `REQUIRES_DATA`, `REQUIRES_DECISION`, `NOT_APPLICABLE`; nothing hidden silently | page tests |
| Units formatted from the catalog `unit` (Rp B, %, sessions) | page tests |
| No formula and no rack download in the page bundle | `tests/bundle/bundle.test.mjs` (after `npm run build`) |

**L8 — Backtest (optional, later):** see 2.9.

**L9 — AI exposure (optional, separate):** see 2.10.

**L10 — Tests:** each layer's suite (section 1.19), plus the class-specific tests in 2.4 to 2.8.

**L11 — Records** (AGENTS.md step 5), in the same task:

| Record | When |
|---|---|
| `DATABASE_CHANGELOG.md`, `DATABASE_SCHEMA.md`, `APPLIED.sha256` | a migration or a data load |
| `RAILWAY_CHANGELOG.md`, `.railway/railway.ts` (every new variable name as `preserve()`; then `railway config plan` until it is up to date; with CLI 5.71 `railway config pull --force` rewrites the whole file, so the deploy runbook adds names by hand, its finding B3) | a deploy, a variable, a service |
| `apps/screener-worker/README.md` "Configuration" | a worker variable is added or its proposed value changes |
| `ERRORS_AND_SOLUTIONS.md` (Part D format; Part A when a lesson changes how data must be shaped) | anything found |
| `BACKTEST_END_TO_END.md`, `apps/edge-bff/backtest/CONTRACT.md` | the publisher's or terminal-api's Backtest-facing behaviour changes, or a Backtest release |
| `UPDATE_TABLE.md` | a manual refresh of a source now has a rack step (flow) |
| `AI_TOOLS.md`, `NEW_TABLE_ONBOARDING_PLAN.md` steps, `DATABASE_INDEX_ACCEPTANCE.md` | the AI reads the table |
| this document | every onboarding: add the metric to Part 1 where it changes the flow; add a lesson to Part 2; a code change that moves a cited line moves its pointer (`npm test` in `apps/screener-worker` fails naming it) |
| `EXEC.md` / `PLAN.md` | approval with the user's words; removal when done |

**L12 — Deploy order (generic; worker first is required):**

1. Migration (DRYRUN, APPLY, read back) and the loader; the source rows verified.
2. screener-worker with everything that reads the file (file list, decoder, binding) and the catalog entries (GitHub
   `main`; any new or raised variable set first and listed as `preserve()`): the new metric appears **disabled**
   (`REQUIRES_DATA`) because no file is indexed yet. Nothing breaks.
3. terminal-publisher (CLI, M248, outside the publisher windows of section 1.19): its next run writes the file and the
   index entry.
4. The worker's next refresh picks the file up, and the metric turns `AVAILABLE` at the next swap without another
   deploy. A skip-unchanged publication (the same price and actions files) only advances `published_at` and keeps the
   availability map (`apps/screener-worker/src/server.ts:278` at a swap, `:296-309` at an advance), so the metric turns
   available with the first publication whose Phase 1 files changed (every daily run with a new session) or at a
   restart.
5. Verify live: the `refresh` line, a screen with the metric, the page. Claim each step only at `SUCCESS` and with the
   read-back.

**Never the other way round.** Availability is derived from the file name in the index alone (section 1.11), so a file
indexed before the worker reads it turns its metrics `AVAILABLE` in the catalog while every run with them is refused
(for flow, `422 METRIC_UNAVAILABLE` at bind, `condition.ts:182`): a refusal the user meets without the rule being shown
first (AGENTS.md "Gates and evidence"). A rollback of the worker after the publisher has the same effect: roll the
publisher back first, or keep the entries' `decision` set until both are live.

## 2.4 Class A: a technical indicator computed from OHLCV

- **Same indicator, other parameters:** nothing to onboard. The dynamic path computes it (section 1.7.3).
- **Arithmetic over existing outputs** (a distance, a ratio, a lag, a rolling extreme, a moving average of an output): a
  transform or pattern, written in screener core (`transforms.ts`: its function, its id in `IMPLEMENTED_TRANSFORMS` or
  `IMPLEMENTED_PATTERNS`, and for a pattern its exact `window` and history class) with its entry in
  `screener-metrics.json`. It is condition arithmetic over `F` outputs, bar fields and the exported `sma`/`ema`, or the
  backtest core's price-action patterns, never a new formula (`transforms.ts` header). It runs on the full series and
  is then tailed by `series()`, so a recursive input stays exact. Its comparison lag comes from the same probe as the
  registry's (a rolling maximum of the high reads the previous bar as the right side of a price comparison; test
  `tests/core/catalog.test.ts` "the comparison lag of rolling_max / rolling_min ..."). The worker prices it as O(N·n)
  over its largest numeric argument (`apps/screener-worker/src/run.ts:152-170`) until the tracker has measured it.
  `screener_engine` changes; the Backtest does not.
- **A new formula** (Ichimoku, or any indicator not among the 53) goes into `F` and `indRegistry.json` through a
  **registry release** (P6, DECIDED with the go), never as a screener transform. Worked example 2.11.

Specific checks:

| Check | Why |
|---|---|
| The convention source is decided: Feature 04 / TA-Lib where one exists, else the reference engine (user 2026-10-25) | one formula contract |
| `F[key]` and `DEFAULTS[key]` added; `indRegistry.json` row with `id`, `key`, `req` (input letters), `outs`, `params` | `build-registry.mjs` refuses a row without a function or a default without a registry parameter |
| Parameters the module does not read are marked as such, not given fake values | they become `not_accepted` |
| Parity: a row in `apps/edge-bff/terminal/tests/calc` fixtures against its oracle (TA-Lib, Feature 04 or the reference engine), PARITY.md updated | the T1 rule: same first valid bar, same nulls, relative difference ≤ 1e-9 |
| Edge cases: flat prices, zero volume, zero range, a single bar, missing bars | the spec's parity section |
| No look-ahead: an output plotted forward (a displaced line) is compared only at the bar it belongs to; the lag probe decides `price_compare_lag` | screening at E must use only bars ≤ E |
| History class and warm-up: recursive or cumulative outputs need full history; cumulative levels are not offered as raw thresholds | section 1.7.3 |
| Cost class derived by the generator (work counted with V8 block coverage at two lengths, never timed) and the cap from `SCREENER_CAP_BUDGET_MS` | `npm run registry:check`; `tests/core/registry-cost.test.mjs` |
| Overlay entry: test forms, `synonyms`, a one-line `description` of our own (20-160 characters), `default_test` | `tests/core/registry.test.ts` "has one entry per base id and vice versa" |
| The new indicator is pre-warmed at its start parameters by the snapshot's loop over the registry (`apps/screener-worker/src/snapshot.ts:266-269`): the pinned series, the replica's memory and the refresh time grow; measure them | the `refresh` line (`pinned_series`, `defaults_ms`, `rss`) |
| Causality and remark edges hold for every output, transform and pattern, checked by loops over the registry and the implemented lists | `tests/core/asof.test.ts`, `tests/core/lookback.test.ts`, `tests/core/params.test.ts` (no new test needed; they must stay green) |

## 2.5 Class B: a flow or broker metric

Sources: `IDX_Broker_Summary` (raw, Stockbit) → Feature 05 (broker, investor type, board, date) → Feature 02 (rolling),
Feature 03 (stock, board, date), Feature 06 (foreign and domestic per board). Refreshed by `stockbit-updater` per token
(`UPDATE_TABLE.md`), not on a schedule. PHASE 2 of the Screener; its decisions are open (P9, P10, P20, D1-D14).

What exists already (BRANCH): the 20 flow entries FL01-FL20 in `screener-metrics.json` (`kind: 'flow'`, a `window` and a
`board` parameter, `requires` `broker_window`, `flow_series` or `actions`, a `decision` where one is open), all
`REQUIRES_DATA` or `REQUIRES_DECISION` today, and the contract's `FlowRef`, `flow_data`, `FLOW_UNAVAILABLE` and
`FLOW_LAGGED`. What PHASE 2 builds: the publisher files, the worker's file list, decoders and flow metrics, the binding
(`condition.ts:182` refuses flow until then), and `flow_data`.

Specific rules (FLOW INDICATOR PROPOSALS 16.3; FACT for the arithmetic):

| Rule | Detail |
|---|---|
| All boards is exact only one way | sum the additive components (IDR values, lots, trade counts, nets) across boards and sessions, **then** compute every ratio, share, ranking, HHI, streak, VWAP, z-score or percentile from the sums. Never add stored per-board windows or ratios (CARE 20-day foreign net: +376.2 B all boards vs −1.5 B Regular) |
| Brokers | sum each broker over both investor types and all boards before ranking or counting |
| Board | `board` (`all` default, `regular` variant) is a parameter on every flow metric; a cell says which |
| Identities | foreign net + domestic net = 0 per (ticker, board, date); stock-level total buy − total sell = 0 (M154): never screen on them |
| Investor type vs domicile | "foreign" is the investor type of the transaction, never the broker's domicile |
| Source gaps | 2016-2020 rows with `source_balance_gap` (M157) are marked, not repaired |
| Completeness gate | a date is published only when F06 (or F03) Regular rows equal the F05 Regular tickers on that date |
| Calendar | stored windows count the ticker's sessions; the Backtest counts price bars; which one a cell uses is P20 and is shown |
| Lag | the cell carries the broker as-of date; `FLOW_LAGGED` beyond the user's maximum (P10) |
| Copies of Backtest formulas (PHASE 2, PROPOSED, not built) | `topNAccumulation` to live in screener core with a test that N = 5 equals `top5Accumulation` (`flow.ts:108`) bitwise; a test to pin `flow.ts`'s hash (TEMPORARY) |
| Grants | F06 or F03 through migration 2 (publisher's own group) |
| Self-check | per board, recomputed sums must equal the stored F06 rows where the ticker has the sessions; a mismatch marks flow `DATA_INTEGRITY` |
| Manual refreshes | after a manual F05/F06 refresh the rack keeps the old flow files until the next publisher run (`UPDATE_TABLE.md` gains that step, PROPOSED) |

Worked example 2.12.

## 2.6 Class C: a fundamental metric

FACT (APPENDIX C.1): no fundamental source exists in the system today. Of the prototype's 32 fundamental metrics none is
available, 2 are derivable (dividend yield and years of dividends, from `idx_event_annotation`), 25 need new data and 5
are bank-only. Fundamental presets ship disabled with reasons (P11). BRANCH: the 32 entries exist in
`screener-metrics.json` (`kind: 'universe'`, `group` `Fundamental`, `requires` the file `fundamentals` or `dividends`,
each with its `unavailable_reason`), served in the catalog's `fundamentals[]`; `catalogProblems` holds their number at
32 (`apps/edge-bff/screener/src/core/catalog.ts:199`), so a 33rd entry changes that check. A fundamental is read as a
field of the worker's universe row (`condition.ts:152-166`): the worker must add it there from the decoded file
(PROPOSED).

Point-in-time requirements (APPENDIX C.6; Part A A2.7; `NEW_TABLE_ONBOARDING_PLAN.md` 2.2):

| Requirement | Rule |
|---|---|
| Report identity | `fiscal_period_end`, period type (Q1 / H1 / 9M / FY), cumulative or de-cumulated, consolidated or parent, audited or not |
| Availability | the filing or publication date and an `available_at` time; a value is usable only after it |
| Restatements | kept as vintages; a restatement never overwrites what was known before |
| Currency and scale | the reporting currency and scale stored with the value; values stored in raw units. FACT: `IDX_Stock_Universe."Fundamental Currency"` is IDR for all 844 stocks, a TradingView attribute; whether USD reporters are converted is UNKNOWN |
| TTM rule | how four quarters are built from cumulative reports, stated as a formula |
| Per-share values | the share count used (weighted or period end), adjusted for splits after the period end, on the same basis as the price |
| Bank vs non-bank | `applies_to` in the catalog: bank-only metrics (NIM, NPL, CAR, CASA, LDR) are `NOT_APPLICABLE` outside `Industry = Banks` (48 banks); metrics meaningless for banks (DER, ROIC, EV/EBITDA, interest cover) are `NOT_APPLICABLE` inside it |
| Staleness | the page shows "period X, published Y" and flags a report older than the user's limit |
| Scope | "today only": a screen at E uses the newest report available at E. No historical screen and no Backtest use until vintages, filing dates and delisted tickers exist (report 6.13) |

Worked example 2.14.

## 2.7 Class D: a macro or cross-asset series

FACT: no FX, policy-rate or commodity table exists. Bond yields do: `Price_Fixed_Income_Final` (a view of
`Price_Fixed_Income`) holds Indonesia and United States government bond prices and yields to maturity
(`Universe_Fixed_income`: 11 Indonesian and 13 US yield tickers), for example `ID10Y` yields from 2016-01-04 to
2026-10-28 (2,679 rows) (live, 2026-10-28). The publisher has no grant on it.

Calendar mismatch is real (FACT, live, 2026-01-01 to 2026-10-28): IHSG has 196 final sessions; `ID10Y` yields 194 dates,
none outside IHSG's sessions and 2 IHSG sessions without a value; `US10Y` yields 204 dates, 16 of them on days IDX did
not trade and 8 IDX sessions without a value.

Specific rules (Part A A2.5-A2.7, A4.17, Part C):

| Rule | Detail |
|---|---|
| One value per date for the whole market | the series is not a column of a ticker; a cell that uses it reports the series' own date |
| Frequency | daily, weekly, monthly, per meeting (a policy rate). A lower frequency is never forward-filled into daily rows in the database; the alignment happens at read time with a declared rule |
| As-of, backward, on availability | for evaluation date E the value is the last observation with `available_at` (release time, or market close + finality delay) at or before the cut time of the publication; never the reference period |
| Time zones | a US close lands on the next Jakarta date; store `timestamptz` or the exchange date with `time_semantics`; the fixed-income pattern keeps `source_bar_time`, `market_close_at`, `is_final` (`Fixed_Income_Market_Schedule`) |
| Revisions and vintages | macro releases are revised: keep vintages, or declare a "latest revision" policy in the catalog and accept that history changes |
| Units and quote convention | percent vs basis points; `USDIDR` = IDR per 1 USD; levels never summed across series; a change is stated as percent or points |
| Staleness | a maximum age per series (for example 5 sessions for a daily series); older is NA with a reason |
| Identifiers | a series code system, upper-case, mapped when sources differ (`USDIDR` vs `IDR=X`) |
| Use in screens | (a) relative: a ticker metric compared with the series over the same window (the `vs_index` pattern); (b) a market-regime gate: one condition on the series alone, the same for every ticker at E |

Worked example 2.13.

## 2.8 Class E: a universe attribute

Today's universe filters come from `ref/tickers.json.gz` (name, type, sector, industry) and from the bars (price, ADV20,
traded on E, history length). Index membership, listing board, special notation, free float, listing date and market cap
have no source (APPENDIX C.8); market cap has its own plan, EXEC-MCAP (`EXEC.md`, waiting for its go).

| Rule | Detail |
|---|---|
| Do not add columns to `ref/tickers.json.gz` casually | FACT: every column after `type` becomes a Backtest portfolio grouping (`publish_refs`, `publisher.py:764`; CONTRACT decision PF6) and a catalog grouping of the Screener (`apps/screener-worker/src/snapshot.ts:97` `groupingsOf`); a numeric column would appear as a grouping with every stock unclassified. A categorical attribute the Backtest should also group by may go there by decision; a numeric one goes into its own xsection file |
| Where the value lives | a field of the worker's universe row (`contract.ts` `UniverseRow`, additive), filled at snapshot build (`snapshot.ts:233-237`) and sent in `GET universe`; a condition reads `row[attr]` (`condition.ts:152-166`); a universe metric filter on a numeric row field runs in S0 on the page and in the worker alike (`universe.ts` `rowAttr`); a categorical filter needs a `UniverseDef` field in `contract.ts` and its rule in `universe.ts`, the one function the page and the worker share. The entries `index_constituents`, `listing_board` and `special_notation` exist (`REQUIRES_DATA`) |
| Category values are real values | no placeholder; a controlled list in a `CHECK`; instrument kind as a type column, never a list of names in code (A1.4, D30) |
| Point in time | membership, board and notation change: keep effective-dated, bitemporal history (A2.8, migration `20260927_006`); never backdate the first capture; a screen at E uses the value valid and recorded at E |
| Unclassified | counted apart, never a value; an include filter keeps it only through an explicit option (P15) |
| Where it acts | stage S0 (conjunctive, outside `met`), so it is safe for every logic and never prunes wrongly |
| Default filters | a default-on filter without data is a silent no-op: it ships off and disabled (the prototype's `exclNotation`, P11) |

---

## 2.9 Making a screener metric a Backtest condition (optional, later)

The user (2026-10-27): "nanti indikator di backtesting bisa kita tambahkan apabila ternyata indikator di screener ini
lebih banyak". FACT: the Backtest accepts three condition kinds (`apps/edge-bff/backtest/src/core/contract.ts:52`,
`Condition = IndicatorCondition | PriceActionCondition | FlowCondition`), flow types `fnet`, `broker`, `top5`
(`FLOW`, `conditions.ts:194-198`), and within-N windows of 1 to 20 bars (`WINDOW_BARS`, `conditions.ts:259`).

To make a screener-only metric transferable:

1. A user decision to change the Backtest (a Backtest release, separate from any Screener phase).
2. The metric's computation moves into (or is generalised in) the Backtest core: a condition kind or flow type in
   `conditions.ts` with its shape in `hash.ts`, the worker's validation (`apps/backtest-worker/src/validate.ts`), the
   page's builder, and `apps/edge-bff/backtest/CONTRACT.md` (section 3 for the request, 4 to 7 for the rules;
   `BACKTEST_END_TO_END.md` section 14 lists the files). The Backtest's `engine_version` changes, deliberately, once.
3. The data must exist for every historical bar the Backtest evaluates, point in time. A metric that is "today only"
   (fundamentals, current-state attributes) stays "screen only".
4. The Screener's copy (for example `topNAccumulation`) is replaced by the core function, and `to-backtest.ts` moves the
   metric from the lossy to the lossless list. Its losslessness test (screener cell = Backtest `conditionSeries[at]` at
   every bar on fixtures) is added.

## 2.10 Exposing the same data to the AI (optional, separate)

The Screener does not need the AI to read a table, and the AI does not read the Screener. If the user also wants the AI
to answer from the new data, follow `NEW_TABLE_ONBOARDING_PLAN.md` end to end, Feature 04 being the benchmark: the 13
visibility links (grant to `market_ai_sql_reader`, `AI_table_catalog`, `AI_column_catalog`, relationships, calculation
rows, coverage, freshness, availability columns, searchable words, prompt and router scope), index acceptance with
`scripts/onboarding/measure_indexes.py` (section 3), the L0-L3 validation, and the generated documents (`AI_TOOLS.md`,
system prompt snapshot) when a tool or prompt text changes. The `screener-metrics.json` fields were chosen to equal the
`Feature_Catalog` fields so that the wording can be reused.

---

## 2.11 Worked example 1: add a technical indicator I54 end to end

Example: Ichimoku Cloud as I54. It is the one indicator the prototype uses that the 53 lack: the catalog's pattern
entries `ichimoku_above` and `ichimoku_tk_cross` carry a `decision` ("needs a registry release", P6), so they and the
`ichi` preset that uses them are `REQUIRES_DECISION` until a registry release (P6 a, decided with the go as the report
recommended: Ichimoku waits for a deliberate registry release with a Backtest worker rebuild).

**Step 0 — approval and definition (user).** Ask for: the outputs (Tenkan, Kijun, Senkou A, Senkou B, Chikou), defaults
(9, 26, 52, displacement 26), the convention source (TA-Lib has no Ichimoku and Feature 04 does not store it, so the
reference is a stated formula and an independent oracle the user accepts), and how the displaced lines are compared (the
cloud value at bar E is the one computed 26 bars earlier: no look-ahead). Record the go in `EXEC.md` as a registry
release; it touches files protected during the Screener build.

**Step 1 — formula and registry (release branch).**
- `apps/edge-bff/terminal/src/calc/indicators.ts`: `F.ichimoku` built with `def(...)` and `DEFAULTS.ichimoku`. Length
  parameters named so that `LENGTH_KEYS` (`indicators.ts:239`) floors them, or typed integer.
- `apps/edge-bff/terminal/src/data/indRegistry.json`: the I54 row (`id`, `cat`, `name`, `key`, `req: "HLC"`, `outs`,
  `params` with `def`, `min`, `step`, the display fields the Terminal reads). The Terminal's indicator list and the
  Backtest page read this file (`apps/edge-bff/terminal/src/main.ts:8`, `apps/edge-bff/backtest/src/reg.ts:5`), so both
  show I54 after the release.
- `npm run registry` in `apps/backtest-worker` → `apps/edge-bff/backtest/src/core/backtest-registry.json` with a new
  `registry_version`; `npm run registry:check` green.

**Step 2 — specification and the AI formula reference.**
- `scripts/terminal_indicator_spec.py`: an I54 row in `I` (formula, outputs, source, TA-Lib none, Feature 04 none).
- OPEN gotcha (FACT from the code): the script regenerates the **applied** migration
  `20261025_102_terminal_indicator_formulas.sql` from every non-Feature-04 row (`migration_sql`, `FIRST_ID` 201), so a
  new row changes that file's text and `--check` fails; editing an applied migration is forbidden. The first registry
  release must split the generator: the I01-I53 rows stay frozen in `20261025_102`, and new rows go into a new forward
  migration (next id INFERENCE: CALC_247, since CALC_201 to CALC_246 hold the 46 non-Feature-04 indicators). Record the
  new `AI_formula_reference` row in `DATABASE_CHANGELOG.md`.

**Step 3 — parity.** Fixtures in `apps/edge-bff/terminal/tests/calc` from the oracle the user accepted (an independent
implementation run by `tools/`), on BBCA, GOTO, IHSG and the random tickers of `PARITY.md`; same first valid bar, same
nulls, relative difference ≤ 1e-9; the edge cases (flat, zero range, short history). `npx vitest run tests/calc`.

**Step 4 — screener registry.**
- `screener-overlay.json`: the I54 entry (`shape`, the test forms per output with operators and labels: close above or
  below the cloud, Tenkan crosses Kijun; `synonyms` "ichimoku", "cloud", "kumo"; a one-line `description` in our own
  words, 20-160 characters; the `default_test`).
- `npm run registry` in `apps/edge-bff/screener` (`build-screener-registry.mjs`) derives the rest: `first_valid_bar`
  (INFERENCE: about 52 + 26 bars for the displaced Senkou B; the probe gives the exact number), `history_class`, units
  (price level, comparable with close), `price_compare_lag`, `inputs` (H, L, C), narrowing, cost class (counted, not
  timed), caps. Then `npm run registry:check` green; `tests/core/registry.test.ts` "has one entry per base id and vice
  versa" fails until this entry exists. `screener_registry_version` changes.
- The two Ichimoku patterns: implement them in `transforms.ts` over I54's outputs (their ids in `IMPLEMENTED_PATTERNS`,
  their exact windows) and remove their `decision` in `screener-metrics.json`; `catalogProblems` fails while an offered
  pattern without a decision is not implemented. The `ichi` preset then has all legs and becomes `AVAILABLE` by
  derivation (`presetAvailability`), computed and pinned at the next swap.
- The snapshot pre-warms I54 at its start parameters with no worker change (the loop over the registry,
  `apps/screener-worker/src/snapshot.ts:266-269`), and the presets' series with it: measure the refresh line's
  `pinned_series`, `defaults_ms` and `rss`.
- Feature 04 oracle: none (`ORACLE`, `scripts/terminal_indicator_spec.py:195`, has no I54 entry); say so with an
  `ORACLE_NOTES` line (`:219`), and re-run `scripts/screener/parity_f04.py --write`: `registry_version` changed.

**Step 5 — tests across consumers.** Terminal calc tests; backtest worker `npm test` (its `registry.test.ts` and
`validate.test.ts` read the registry); Backtest page vitest and smoke; screener core tests (VALUE, STATE, EVENT on I54;
default = dynamic at default parameters bit for bit; the loops of `params.test.ts`, `asof.test.ts` and
`lookback.test.ts` cover I54 by themselves); screener-worker `npm test`; the tripwire reports the expected
`registry_version` change, which the release record names (and `backtest_worker_baseline.json` is recorded again for
the rebuilt worker).

**Step 6 — deploy (one release window, outside 00:00-01:45 and 12:00-13:20 UTC).**
1. Merge to `main`: edge-bff (Terminal and Backtest pages, Screener page) and screener-worker redeploy from GitHub
   (check the merge commit was deployed, M252; the worker's watch patterns include `indicators.ts` and
   `indRegistry.json`, and its start-up check refuses a stale `screener-registry.json`, so a worker built from a
   half-released tree never starts).
2. Deploy the backtest worker from the merge commit by CLI (M248). INFERENCE: until it is live, the Backtest page offers
   I54 while the old worker refuses it; keep the window short and say so in the release record.
3. Read back: the worker's `/health` shows the new `registry` and `screener_registry`; the catalog lists I54; a screen
   with I54 and a Backtest run with I54 both work; the Terminal draws it.

**Step 7 — records.** `RAILWAY_CHANGELOG.md` (the three deployments at SUCCESS), `DATABASE_CHANGELOG.md` (the formula
row), `ERRORS_AND_SOLUTIONS.md` (anything found), `BACKTEST_END_TO_END.md` section 14 and `CONTRACT.md` if a rule
changed, this document, `EXEC.md`. Saved screens are unaffected (a release only adds an id).

## 2.12 Worked example 2: add a flow metric (FL10, net-buy concentration HHI)

From FLOW INDICATOR PROPOSALS 16.5: "whether the stock's net buying over D sessions is held by one or two brokers (near
1) or spread over many (near 0)". PHASE 2, PROPOSED; the user picks the Phase 2 set (D1) and the HHI basis (D3: net-buy
HHI recommended). Its catalog entry already exists (`net_buy_hhi`, `fl` FL10, `REQUIRES_DATA`); what is missing is the
data file and the worker's computation.

**Definition.** For a stock over the last D sessions ≤ t (default D = 20, range 1-20): each broker's net n_b summed over
both investor types and all boards (unless `board = regular`); H = Σ_{b: n_b > 0} (n_b / Σ_{n_b > 0} n_b)²; effective
number of net buyers = 1/H. NULL when no broker is a net buyer. Unit: fraction 0-1. FACT (live, 2026-10-27, D = 20, 828
stocks): median 0.222; BBCA 0.095 (10.5 effective buyers), ANTM 0.110, CARE 0.401.

**L1 PostgreSQL.** No new table: F05 already holds every (ticker, date, broker, investor type, board) row and the
publisher can read it. Checks: F05 dates complete (the completeness gate); `buy_freq`/`sell_freq` not needed for FL10.
Measured cost of the whole-universe 20-session read: 3.96 s in an `EXPLAIN (ANALYZE, BUFFERS)` (`trade_date_idx`,
487,715 rows; 16.7.1); the production path reads per date with literal bounds (about 2 s per new date cold,
incremental).

**L2 publisher.** The Phase 2 `broker_window` file (41 complete sessions = D ≤ 20 + within ≤ 20 + 1), raw F05 rows in
the existing broker encoding, decodable by `brokerRows` (`datafile.ts:183`). About 1.0 M rows, 8-12 MB gzip (INFERENCE).
Rebuilt by `daily` when `broker_through` moves, by `broker-range` after a manual broker refresh.

**L4 catalog.** The entry as it stands in `screener-metrics.json` (BRANCH; shortened: `params` also carry `label`,
`exclusive_min`, `integer`, `step`):

```
{ "id": "net_buy_hhi", "group": "Flow", "kind": "flow", "label": "Net-buy concentration (HHI)", "fl": "FL10",
  "params": [{"key": "window", "type": "integer", "default": 20, "min": 1, "max": 20},
             {"key": "board", "type": "enum", "default": "all", "options": ["all", "regular"]}],
  "tests": ["value"], "unit": "x",
  "requires": {"file": "broker_window", "columns": ["d", "b", "i", "m", "bv", "sv", "bl", "sl"]},
  "decision": null, "applies_to": null,
  "unavailable_reason": "Flow metrics arrive with Phase 2 (all trading boards by default).",
  "formula": "sum over net buyers of (n_b / sum of positive n_b)^2 over D sessions",
  "interpretation": "Near 1: one broker holds the net buying; near 0: spread over many.",
  "misuse": "Merger-guideline levels do not apply; higher for illiquid stocks.",
  "evidence": "report FLOW INDICATOR PROPOSALS (PHASE 2) 16.5 FL10" }
```

When Phase 2 builds it: the `evidence` becomes the parity record, and the `misuse` text can carry the proposal's full
warning (says who holds the net buying, not how large it is: pair it with Bandar balance; not the stored 1-day |net|
HHI of broker flow). The `max` 20 is derived from the published window (41 sessions), not typed into code. A companion
entry (1/H, unit "brokers") can share the computation.

**L5 worker (PROPOSED).** `broker_window` joins the worker's file list as an optional file (a missing Phase 1 file fails
the refresh, `refresh.ts:264-266`, so Phase 2 needs its own rule), with its decoder (`brokerRows`), its `flow_data`
version and a place in `sid`; the flow binding replaces the refusal at `condition.ts:182`; a `flowmetrics.ts` in the
core: per ticker, per broker, sum n_b over the window on the chosen calendar (P20, D12); compute H; NA
`NULL_AT_EVALUATION` when there is no net buyer; `FLOW_LAGGED` beyond the broker lag limit (P10); the cell's `eval_date`
is the broker as-of date. One ranking pass serves FL07-FL10 (16.10). Cost INFERENCE: about 30-40 ms for a custom D over
the universe; the cost model needs its unit for it (`run.ts` `costUnits`).

**Tests.** Parity against the bounded SQL of the proposal (`q13`, one date) on a sample; all-board vs Regular fixture (a
Nego-only broker changes H only on `all`); a stock with no net buyer → NA; D boundaries (1 and 20 pass, 21 refused with
`PARAM_OUT_OF_RANGE`); removing `broker_window` from a fixture index turns FL10 `REQUIRES_DATA`.

**L7 page.** Label "Net-buy concentration (HHI)", unit as a fraction with the effective-buyers figure beside it; the
misuse text in the tooltip; thresholds labelled unvalidated (D10).

**L8 Backtest.** Not transferable (no Backtest condition); `to-backtest.ts` lists it in `left_out` with the reason.

**Deploy.** Migration 2 only if the Phase 2 set also needs F03/F06; the worker that reads and computes it first (the
entry stays disabled until the file exists); then the publisher with `broker_window`; verify (2.3 L12: never the
publisher first). Records: `UPDATE_TABLE.md` gains the rack step after a manual broker refresh.

## 2.13 Worked example 3: add a macro series (USD/IDR daily close)

PROPOSED throughout; no FX source exists (FACT). Two uses: a filter "stock vs USD/IDR" (relative performance, the
`vs_index` pattern) and a market-regime gate ("only screen when the rupiah weakened less than 2% over 20 sessions").

**Step 0 — decisions with the user.**
- Source and licence; which price: a market close (24/5 FX market, close in another time zone) or an official fixing on
  IDX business days (for example Bank Indonesia's JISDOR; its publication time to be checked with the source). The
  fixing follows the IDX calendar and avoids the time-zone question; a market close needs the as-of rule below.
- Quote convention (`USDIDR` = IDR per 1 USD), unit (IDR), and whether "rupiah weakens" means USDIDR rises (yes).
- Maximum staleness (for example 5 IDX sessions) and the behaviour beyond it (NA with a reason).

**L1 PostgreSQL (house pattern of fixed income).**
- A universe of series: `Universe_FX` (PROPOSED name): `ticker` (`USDIDR`), quote convention, unit, source symbol,
  market, time zone, close time, calendar; `CHECK` lists for fixed values.
- A value table: `Price_FX`: `(ticker, date, "Timeframe")` key, `open/high/low/close` numeric, `source_bar_time`,
  `market_close_at`, `is_final`, `finalized_at`, `ingestion_time`, `source`; a schedule table like
  `Fixed_Income_Market_Schedule` (time zone, local close, finality delay); a view `Price_FX_Final` (`is_final` daily
  rows only). Index led by `date` if the table can exceed 2,000,000 rows; measure the cross-section and window patterns.
- Catalogs: `Table_Catalog`, `Column_Catalog` (unit IDR per USD, `time_semantics` with the time zone and close),
  `AI_table_catalog` subject metadata (`data_domain` FX, `entity_type` CURRENCY_PAIR, frequency `1D`) only if the AI
  reads it.
- Loader: an app like `fixed-income-price-cron`, with a load log and an alert; schedule after the source's close.
- Grant: the publisher's own read group gains SELECT on the view (the base table stays hidden).

**L2 publisher.** An xsection file `fx` (or one `series` file for every macro series): columns `s` (series), `d` (date),
`v` (value), `avail` (the availability time used for as-of), full history, `units` per series, `as_of` = the cut time of
the run. Rebuilt when the series' stamp changes. Verify against SQL.

**As-of rule (Part A A2.7, A4.17).** For evaluation date E, the value is the last final observation whose `avail` is at
or before the publication's cut time and whose date is on or before E. A market close in New York (INFERENCE, for a
source whose daily bar closes at 17:00 New York, about 04:00-05:00 WIB the next day) lands after the 19:00 WIB run of
the same date, so that run uses the previous close and the 07:30 WIB run picks the new one up (the two runs of one day
can differ; the cell's `eval_date` says which value was used). FACT behind the rule: the calendars differ (section 2.7:
`US10Y` has 16 values on non-IDX days and lacks 8 IDX sessions in 2026).

**L4 contract and catalog.**
- A new wire kind, the first time a market-wide series is used (PROPOSED, an additive change to `contract.ts`
  `MetricRef` and `MetricKind`, and to the kinds `catalog.ts:152` `KINDS` accepts): `{kind: 'series', series:
  'USDIDR', field: 'close'}`, valid series read from the catalog; its binding in `condition.ts` and its validation in
  `validate.ts` are new code.
- Transform `vs_series` (generalising `vs_index`): the stock's return over d sessions minus the series' return over the
  same dates, aligned by the as-of rule; or, if the user prefers, the stock's return in USD terms ((1 + r_stock) / (1 +
  r_fx) − 1). Which one is a user decision; the catalog entry states the formula.
- Market-regime gate: a VALUE test on the series alone (for example `change(USDIDR, 20) < 2%`). PROPOSED semantics, to
  settle with the user: the gate runs in S0, once per screen, outside `met`; when it fails the screen returns no rows
  and a warning that names the gate, its value and its date (a gate counted in `met` would make near misses meaningless,
  because it fails for every ticker at once).
- NA and remarks: `SERIES_STALE` (PROPOSED NA reason) when the newest value is older than the limit; wording in
  `texts.ts`.
- Entries: `requires {file: 'fx', columns: ['s','d','v','avail']}`, `unit` IDR per USD or percent for a change,
  `periods` reused.

**L5 worker (PROPOSED).** The file in the worker's file list (optional), its decoder, staleness check, alignment to
IHSG's calendar with `asOf` (`datafile.ts:259`, the function the Backtest uses for IHSG), the series' data version
beside `price_data` and in `sid`. Tests: a holiday on one calendar only, a value published after the cut time, a stale
series, the gate failing.

**L8 Backtest.** Possible later (the series has history), through a Backtest release with the same as-of rule.

**Deploy and records** as in 2.3 L11-L12. Part C of ERRORS lists the checks before go-live: a sample of dates where the
joined value must be the one published by then; one known holiday; one converted value equal to a manual conversion.

## 2.14 Worked example 4: add a fundamental metric (ROE TTM) with point-in-time rules

PROPOSED throughout; no statement source exists (FACT, APPENDIX C.1).

**Step 0 — decisions with the user.** Source and licence (IDX filings, a vendor, Stockbit keystats: none is used today);
the definition: ROE TTM = net income attributable to the parent over the last four quarters ÷ equity attributable to the
parent (average of the start and end of the window, or ending equity: a user choice); consolidated statements; negative
equity → NA; banks included (ROE applies to banks); how cumulative reports become quarters; the staleness limit.

**L1 PostgreSQL.**
- `Fundamental_Statement` (PROPOSED name): one row per (ticker, `fiscal_period_end`, `period_type` CHECK in Q1, H1, 9M,
  FY, `consolidation` CHECK in CONSOLIDATED, PARENT, `item` CHECK list, `vintage`), `value` numeric in raw units,
  `currency`, `is_cumulative`, `audited`, `filed_at` (the publication date), `available_at` (when Saniti had it),
  `source`, `source_document_id`, `ingestion_time`. A restatement is a new `vintage`, never an update.
- A Feature table for the derived metric, named `Feature_NN_...` (the `Feature_Catalog` trigger refuses another name,
  ERRORS M202): one row per (ticker, `available_at`) with `roe_ttm`, `ttm_net_income`, `avg_equity`, the four
  `fiscal_period_end`s used, the `vintage`s used, and `is_complete`; `Feature_Catalog` rows (formula, interpretation,
  recommended use, misuse warning, evidence), `scripts/audit_feature_catalog_semantics.py`.
- Validation against an independent sample of filings before `semantic_review_status` leaves its draft value.

**L2 publisher.** An xsection file `fundamentals`: per ticker the newest row with `available_at` at or before the cut
time: `roe_ttm`, the latest `fiscal_period_end`, `filed_at`, currency. "Today only": no history in the file.

**L4 contract and catalog.**
- No new wire kind: a fundamental is `{kind: 'universe', attr: 'roe'}`
  (`apps/edge-bff/screener/src/core/contract.ts:460-462`). The entry exists (BRANCH: `id` `roe`, `group` `Fundamental`,
  unit `%`, `requires {file: 'fundamentals', columns: ['roe']}`, formula "net income (TTM) / average equity x 100"); it
  is served in the catalog's `fundamentals[]` and turns `AVAILABLE` by derivation once the file is indexed. Change its
  `formula` to the definition the user settles (TTM, average or ending equity) and its `misuse` to "ROE is inflated by
  leverage and by small or negative equity; compare within an industry"; `applies_to` stays null (all stocks; for a
  bank-only metric `Industry = Banks`).
- NA reasons: `INSUFFICIENT_HISTORY` (fewer than four quarters), `NOT_APPLICABLE`, and a staleness reason
  (`REPORT_STALE`, PROPOSED) beyond the limit; the cell carries `period` and `published` for the page.

**L5 worker (PROPOSED).** `fundamentals` joins the worker's file list (optional); its decoder writes `roe` (and its
`period` and `published`) as fields of each universe row at snapshot build (`contract.ts` `UniverseRow`, additive), so
the existing binding reads it (`condition.ts:152-166`: a missing or non-finite value is NA) and `GET universe` carries
it; staleness check; tests with a restated report (the newest vintage available at E wins), a report filed after E (not
used), a bank and a non-bank.

**L7 page.** "ROE TTM 18.2% · period 2026-06-30, published 2026-07-29"; stale reports flagged; fundamental presets turn
on only when every leg is available.

**L8 Backtest.** "Screen only" until vintaged history and delisted tickers exist (report 6.13).

**L9 AI.** If the AI should read fundamentals, `NEW_TABLE_ONBOARDING_PLAN.md` (fundamental row of 2.2) and the prompt's
`OUTSIDE_DATA_RULE` (which tells the model fundamentals are outside the catalog) change in that onboarding.

---

# Part 3 — Quick reference

## 3.1 Where things live

| What | File |
|---|---|
| Indicator formulas and defaults | `apps/edge-bff/terminal/src/calc/indicators.ts` (`DEFAULTS` line 215, `F` line 277) |
| Indicator registry (Terminal) | `apps/edge-bff/terminal/src/data/indRegistry.json` |
| Backtest registry and its generator | `apps/edge-bff/backtest/src/core/backtest-registry.json`; `apps/backtest-worker/scripts/build-registry.mjs` |
| Parameter contract, `Calc`, conditions | `apps/edge-bff/backtest/src/core/registry.ts` (`resolveParams` line 46), `conditions.ts` |
| File decoding, data version, as-of | `apps/edge-bff/backtest/src/core/datafile.ts` |
| Indicator specification, AI formula rows, oracle map | `scripts/terminal_indicator_spec.py` |
| Formula parity record | `apps/edge-bff/terminal/tests/calc/PARITY.md` |
| Publisher | `apps/terminal-publisher/publisher.py` |
| terminal-api | `apps/terminal-api/app/main.py`, `bucket.py`, `quota.py` |
| Publisher and terminal-api logins | `scripts/provision_terminal_logins.py`; migrations `20261025_100`, `20261025_101` |
| Screener contract | `apps/edge-bff/screener/src/core/contract.ts` (BRANCH) |
| Screener overlay and generated registry | `apps/edge-bff/screener/src/core/screener-overlay.json`, `screener-registry.json`, `registry.ts` (BRANCH) |
| Screener metric catalog, presets | `apps/edge-bff/screener/src/core/screener-metrics.json`, `presets.json`, `catalog.ts` (BRANCH) |
| Screener series path, transforms, evaluation, planner | `apps/edge-bff/screener/src/core/metrics.ts`, `transforms.ts`, `condition.ts`, `evaluate.ts`, `match.ts`, `plan.ts`, `screen.ts`, `xsection.ts`, `universe.ts`, `validate.ts` (BRANCH) |
| Screener generator | `apps/edge-bff/screener/scripts/build-screener-registry.mjs` (BRANCH) |
| Worker | `apps/screener-worker/src/` (`server.ts`, `refresh.ts`, `snapshot.ts`, `pool.ts`, `thread.ts`, `run.ts`, `preview.ts`, `catalog.ts`, `config.ts`, `version.ts`), `README.md` (variables and their proposed values), `CONTRACT.md`, `Dockerfile` (BRANCH) |
| edge-bff module and tables | `apps/edge-bff/app/screener.py`, `config.py`; `database/migrations/20261028_001_edge_bff_screener.sql` (BRANCH, not applied); its jobs in `verification/screener/jobs/` |
| Cross-sectional files at the publisher and terminal-api | `apps/terminal-publisher/publisher.py` (`XSECTION_REBUILT_BY`, `publish_xsection`, `xsection_entries`, `verify_xsection`); `apps/terminal-api/app/bucket.py` `xsection_index`, `main.py` `xsection`, `xsection_caller` (BRANCH) |
| Page and its words | `apps/edge-bff/screener/src/`, `src/texts.ts`, `src/app.ts` (load sequence), `src/api/boot-cache.ts` (BRANCH) |
| Tripwire, parity, timing | `scripts/screener/check_backtest_untouched.mjs` (+ `backtest_worker_baseline.json`), `scripts/screener/parity_f04.py`, `verification/screener/page_timing_dev.py` |
| Records | `verification/screener/AUDIT.md` (the approval-gate report), `F04_PARITY.md`, `BENCHMARK_LOCAL.md` (LOCAL); `BENCHMARK.md` and `E2E.md` after the dev deploy |
| Data-format standard | `ERRORS_AND_SOLUTIONS.md` Part A, Part C |
| AI onboarding | `NEW_TABLE_ONBOARDING_PLAN.md`, `scripts/onboarding/` |

## 3.2 One-page checklist

1. Approval with the user's words in `EXEC.md`/`PLAN.md`; class chosen (2.1); Part A gaps settled.
2. PostgreSQL: migration, indexes measured, catalogs, publisher grant, loader and monitoring (2.2).
3. Publisher: deterministic xsection file, index entry, rebuild rule, verify, size measured (2.3 L2).
4. Catalog: registry release (A) or `screener-metrics.json` entries; availability derived; new kinds or NA reasons with
   all four gate items (2.3 L4).
5. Worker: decoder, checks, units, alignment, version, memory and time measured (2.3 L5).
6. Page: texts, disabled states, units (2.3 L7).
7. Tests at every layer; tripwire green unless this is a registry or Backtest release.
8. Deploy in order; claim at `SUCCESS` with a live read-back (2.3 L12).
9. Records: changelogs, ERRORS, this document, `EXEC.md` (2.3 L11).

## 3.3 Glossary

- **Rack**: the published files in the `terminal-display` bucket that Terminal, Backtest and Screener read.
- **Publication**: one finished publisher run, named by `state.json` `finished_at`.
- **xsection file**: a whole-universe file (every ticker in one document), content-addressed.
- **Snapshot**: the worker's in-memory state for one publication: bars, default indicators, attributes, ranks, preset
  results.
- **E (evaluation date)**: `price_through` of the publication.
- **Registry release**: a deliberate change of `indicators.ts` and `indRegistry.json`, with the Backtest registry
  rebuilt and the backtest worker redeployed.
- **Availability**: `AVAILABLE`, `REQUIRES_DATA`, `REQUIRES_DECISION`, `NOT_APPLICABLE`, derived at run time from the
  index and the catalog.
- **As-of, backward**: the last observation available at or before a time; never a later one.
- **WIB**: UTC+7 (the publisher runs at 07:30 and 19:00 WIB = 00:30 and 12:00 UTC).
