# EDGE Screener: how it works, and how to onboard a new indicator or dataset

How the EDGE Screener works, from the rows in PostgreSQL to what the browser page draws (Part 1), and what to check in
every layer when you add an indicator, a metric or a whole dataset (Part 2): technical, flow, fundamental, macro or a
universe attribute. Written for the next agent or person who onboards something new. Read Part 1 once, then follow the
Part 2 checklist for your data class.

The user asked for it on 2026-10-28 (`EXEC.md` EXEC-SCREENER): "nanti siapkan dokumentasi sama how screener ini works
dan workflow kalau mau tambah indikator (apa requirementnya di postgres, table apa yang harus disiapkan) goalnya adalah
MD itu bisa dijadikan onboarding documents apa yang mesti di cek di service dll to onboard new documents (bukan hanya
technical, tapi ada macro juga dll)".

- **Status: written during Phase 1.** The Screener was approved on 2026-10-28 (`EXEC.md` EXEC-SCREENER, "go") and is
  being built on the branch, phase by phase, on dev. At the time of writing nothing of it is deployed. Everything the
  Screener adds is labelled **PROPOSED** (designed, not built) or **BRANCH** (code on the working branch, not deployed,
  not verified live) below. **This document is updated when Phase 1 lands** (and again at Phase 1b and Phase 2): change
  each label that became true into a FACT with its file, deployment ID or measurement, in the same change that lands it.
- **Verified against:** the repository at commit `9a6cddc` (branch `claude/charming-hamilton-faq25e`, 2026-10-28) for
  every existing file, plus the uncommitted publisher work seen in the working tree the same day; the approval-gate
  report of the Screener (to be committed as `verification/screener/AUDIT.md`; cited by section name: TARGET
  ARCHITECTURE 6.x, PAGE LOAD SEQUENCE 6c.x, MULTI-USER SCALE AND COST 6d.x, DATABASE / FEATURE CHANGES 7.x, API
  CONTRACT 8.x, TEST PLAN 10b.x, UNKNOWNS / PRODUCT DECISIONS 13.x, FLOW INDICATOR PROPOSALS 16.x, APPENDIX C) for the
  design; read-only live PostgreSQL checks of 2026-10-28 where a line says "live".
- **Pointers** are `path:line` at `9a6cddc` plus the symbol. Lines move: when a line does not match, search for the
  symbol. Files the Phase 1 build is still writing (for example `apps/edge-bff/screener/src/core/contract.ts`) are cited
  by symbol only.
- **Labels.** FACT: seen in code on `main` or deployed, in data, or in a recorded measurement. BRANCH: code committed on
  the working branch, not deployed and not verified live (its behaviour still counts as PROPOSED). PROPOSED: the
  approved design, not built yet. INFERENCE: derived, not stated or implemented directly. DECIDED: a user decision, with
  its date. OPEN: a known problem or a question without an answer. TEMPORARY: a stopgap a user decision allowed for now.
- **Where the other details live:**
  - `BACKTEST_END_TO_END.md`: the rack (publisher, bucket, terminal-api) and the Backtest, which the Screener reuses.
    This document does not repeat its sections 3 to 6.
  - `apps/edge-bff/backtest/CONTRACT.md`: the Backtest's rules; `apps/edge-bff/screener/src/core/contract.ts` and
    (PROPOSED) `apps/screener-worker/CONTRACT.md`: the Screener's wire contract.
  - `ERRORS_AND_SOLUTIONS.md` Part A: the data-format standard every new source must meet; Part C: the risks of macro
    and cross-asset data.
  - `NEW_TABLE_ONBOARDING_PLAN.md`: how a table becomes visible to the AI (a separate onboarding, section 2.10 below).
  - `DATABASE_CATALOG.md`: catalog roles and the mandatory maintenance after any schema change.
  - `EXEC.md` EXEC-SCREENER: the approvals and the decisions P1 to P28.
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
   per-ticker files, packs, manifests ............ unchanged (Terminal, Backtest)
   ref/tickers.json.gz (name, type, sector, industry)  reused by the Screener
   + xsection/price.<sha16>.json.gz, xsection/actions.<sha16>.json.gz ....... PROPOSED, Phase 1
   + xsection/flow files ................................................... PROPOSED, Phase 2
   state.json (written last) + its xsection index ......................... PROPOSED
        ▲ bucket credentials (terminal-api only reads and presigns)
 terminal-api (sfo): GET /state (exists) + xsection index (BRANCH); POST /xsection (BRANCH, proxy key only)
        ▲ x-terminal-proxy-key, private network
 screener-worker (PROPOSED new service, Node 22, sfo, private, no DB or bucket credentials)
   per publication: download changed xsection files, verify sha256, build the snapshot
   (all 53 indicators at defaults, universe attributes, ranks, preset counts), swap all-or-nothing;
   per request: custom parameters, condition engine, planner, near misses, caches
        ▲ x-screener-worker-key, private network
 edge-bff (FastAPI): /api/v1/screener/* (session cookie; Origin + CSRF on writes); relays bytes;
   saved screens, My metrics, one watchlist in edge_bff tables (PROPOSED)
        ▲ same origin
 browser: EDGE /screener → iframe /screener-app/ (PROPOSED): renders only, no formula code,
   connect-src 'self' (never the bucket)
```

In one paragraph: the Screener reads no market table at request time. Twice a day the existing terminal publisher,
besides the per-ticker files the Terminal and the Backtest read, writes a few whole-universe ("cross-sectional",
xsection) files and names them in `state.json`. A new private service, `screener-worker`, notices the new publication
through terminal-api's `/state`, downloads only the files it does not hold, checks their sha256, and computes every
indicator at its default parameters for every ticker once, in memory. A screen is then mostly lookups: custom parameters
are computed on demand only for the tickers that can still match. edge-bff authenticates the browser and relays the
worker's answers; it stores only the user's own objects (saved screens, the watchlist). The page draws what it is given.
Terminal, Backtest and Screener therefore always show the same publication of the same data.

## 1.2 Parts, where they run, what they hold

| Part | Code | Status | Runs as | Holds | Never |
|---|---|---|---|---|---|
| Market tables | `database/migrations/`, `DATABASE_SCHEMA.md` | FACT | Railway `Postgres` (sfo) | the source rows | — |
| terminal-publisher | `apps/terminal-publisher/publisher.py` | FACT; xsection writer PROPOSED | Railway cron, CLI upload, sfo | read-only DB login, bucket write credentials | serves readers |
| Bucket `terminal-display` | written by the publisher | FACT | Railway bucket, sin | every published file | — |
| terminal-api | `apps/terminal-api/app/` | FACT; `xsection` on `/state` and `POST /xsection` BRANCH (`9a6cddc`) | FastAPI, CLI upload, sfo | bucket credentials, quotas and audit (schema `terminal`) | streams a data file |
| Shared formulas | `apps/edge-bff/terminal/src/calc/indicators.ts`, `terminal/src/data/indRegistry.json` | FACT, unchanged by the Screener | TypeScript, imported | the 53 indicator formulas and their registry | — |
| Backtest shared core | `apps/edge-bff/backtest/src/core/` | FACT, unchanged by the Screener | TypeScript, imported | parameter contract (`registry.ts`), `Calc`, `compare`, patterns, flow helpers, file decoding | — |
| Screener core | `apps/edge-bff/screener/src/core/` | BRANCH: `contract.ts`, `screener-overlay.json`, the generated `screener-registry.json` and its generator `scripts/build-screener-registry.mjs`; the rest PROPOSED | TypeScript imported by the worker and (two files) the page | contract, validation, metrics, transforms, evaluation, planner, catalogs | defines an indicator formula |
| screener-worker | `apps/screener-worker/` | PROPOSED (DECIDED P3 a, 2026-10-28) | Node 22, GitHub `main`, sfo, private | `TERMINAL_PROXY_KEY`, `SCREENER_WORKER_KEY`, the in-memory snapshot | Postgres or bucket credentials |
| edge-bff Screener module | `apps/edge-bff/app/screener.py`; migration `database/migrations/20261028_001_edge_bff_screener.sql` | module being written; migration BRANCH (not applied) | FastAPI, GitHub `main` | the relay, saved items (`edge_bff.screener_items`, `edge_bff.watchlist_items`) | computes a screen, stores market data |
| Page | `apps/edge-bff/screener/` (Vite + TypeScript) | BRANCH: scaffold and first modules (`texts.ts`, `state.ts`, `forms.ts`, `api/live.ts`, …); the port is in progress | static files in edge-bff at `/screener-app/` | nothing secret | formula code, rack downloads |
| Feature 04 | `features/feature04/`, `apps/feature-04-worker/` | FACT, unchanged (DECIDED P2 a) | its own worker | stored indicators for the AI | read by the Screener at run time |

## 1.3 Rules that shape every part

From the user's decisions (DECIDED 2026-10-28, `EXEC.md` EXEC-SCREENER) and the design invariants (TARGET ARCHITECTURE
6.1). Every onboarding must keep them true.

1. **One source, the rack (P1 a).** Market data reaches the Screener only through files of the 07:30 / 19:00 WIB
   publication. No request reads PostgreSQL market tables. The Screener shows exactly the session the Terminal and the
   Backtest show; between the price cron (17:00 WIB) and the end of the 19:00 run the database holds a session the rack
   does not (about 3 hours, TARGET ARCHITECTURE 6.5).
2. **One formula path (I1).** Every technical number comes from `F` in `indicators.ts` through the Backtest core's
   `Calc`. There is no SQL, TA-Lib or Python copy of a formula. A test fails if a screener file defines an indicator
   kernel (PROPOSED).
3. **The Backtest is untouched (I3).** No byte changes in `indicators.ts`, `indRegistry.json`, `backtest-registry.json`
   or `apps/edge-bff/backtest/src/core/**` during the Screener build; `apps/backtest-worker/**` changes only as a
   recorded approval says (EXEC-MU-RUNTIME: `scripts/screener/backtest_worker_baseline.json` names the approved worker
   tree, its versions and the EXEC section; any other worker change fails the tripwire). Why: the Backtest's
   `engine_version` hashes every core file (`apps/backtest-worker/src/version.ts:18-21`, `SOURCES`) and its
   `registry_version` hashes `indRegistry.json` plus `indicators.ts`
   (`apps/backtest-worker/scripts/build-registry.mjs:24`, `registryVersion`); either change alters every Backtest result
   key, and a stale registry stops the backtest worker at start (`apps/backtest-worker/src/server.ts:348-349`,
   `registry_mismatch`). A tripwire script checks it (PROPOSED: `scripts/screener/check_backtest_untouched.mjs`). New
   indicators therefore arrive only through a deliberate **registry release** (P6, section 2.4).
4. **Feature 04 is unchanged and is not read at run time (P2 a).** It is the parity oracle in tests (section 1.12).
5. **Nothing fabricated (I5).** Every cell is PASS, FAIL or NA, and every NA carries a reason code. A metric without
   data is shown disabled with its reason, never silently dropped.
6. **No silent adjustment (I7).** Invalid input is refused with the field and the fix; never clamped, rounded or
   reordered.
7. **Versions in every answer (I6).** Each answer names the data, engine and registry versions that produced it (section
   1.13).
8. **Stale tickers and unadjusted price breaks are hidden by default (P4, P4.1 A).** Shown through a chip, their rows
   carry a remark with the reason, and their values stay visible with a cell remark.
9. **Flow uses all boards by default (P8 b)**, with a labelled Regular variant (Phase 2).
10. **The user's objects live in `edge_bff` tables (P12 a)**: saved screens, My metrics, one watchlist.
11. **Multi-user and cost:** what depends only on the publication is computed once and shared by every user (section
    1.16). **Page load** follows the Terminal and Backtest pattern: draw at once, load what is needed, use answers kept
    per publication (section 1.9).

## 1.4 Stage 1: PostgreSQL

The Screener never queries PostgreSQL for market data. What it uses reaches it through the publisher, which reads with
the read-only login `terminal_publisher_login` (member of `terminal_market_reader` only;
`default_transaction_read_only on`, `statement_timeout 120s`, connection limit 4:
`scripts/provision_terminal_logins.py:15-31`).

| Table | Read today by the publisher (FACT) | Used by the Screener for | Phase |
|---|---|---|---|
| `Price_Stock_Indonesia_IDX` (`timeframe = 'Daily' AND is_final`) | per ticker-year (`PRICE_SQL`, `publisher.py:55`) | whole-universe bars in the `price` xsection file: one statement without the ticker filter (about 2.0 s seq scan, report 6.5; PROPOSED) | 1 |
| `IDX_Stock_Universe` | the reference file `ref/tickers.json.gz` (`UNIVERSE_SQL`, `publisher.py:96`; `publish_refs`, `publisher.py:418-431`) | name, type, sector, industry, read from the existing reference file (not copied) | 1 |
| `idx_event_annotation` | per-ticker events files (`EVENTS_SQL`, `publisher.py:67`) | the `actions` xsection file: price-affecting corporate actions (for the price-break remark) and cash dividends (Phase 2 dividend metrics) | 1 |
| `Feature_05_Foreign_Domestic_Broker_Detail` | per-ticker broker files (`BROKER_SQL`, `publisher.py:58`) | the `broker_window` file (41 complete sessions) for broker-ranking metrics | 2 |
| `Feature_06_Foreign_Domestic` or `Feature_03_Stock_Broker_Daily` | **not readable** by the publisher (live L1: no SELECT on F06 or F04) | the long all-board foreign-flow series; needs a new NOLOGIN read group by forward migration (migration 2, report 7.2; the source table is decision D9 of FLOW INDICATOR PROPOSALS 16.11) | 2 |

What the Screener adds to the database (PROPOSED, report 7.2):

- **Migration 1 (Phase 1; BRANCH, not applied: `database/migrations/20261028_001_edge_bff_screener.sql`):**
  `edge_bff.screener_items` (kind `screen` or `metric`, definition as `jsonb` up to 65,536 bytes, versions, `revision`)
  and `edge_bff.watchlist_items` (`owner_key`, `ticker`), in the house style of the `edge_bff` migrations
  (`database/migrations/20261026_005_edge_bff_backtest.sql`: preflight, comments, exact grants, a `$verify$` block, the
  rollback as a comment). No public table changes.
- **Migration 2 (Phase 2):** role `terminal_publisher_feature_reader` (NOLOGIN) with SELECT on the chosen flow table,
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
  (ERRORS M238, OPEN).
- Prices are stored as received: back-adjusted for splits before 2026-09-12, raw after it (`ADJUSTED_HISTORY_BOUNDARY`,
  `apps/edge-bff/backtest/src/core/engine.ts:157`; ERRORS D22, OPEN). Eight tickers had a price-affecting action between
  that date and 2026-10-27 (live L6, report 6.12).
- Broker data trails prices until a new Stockbit token starts a round (ERRORS M243).
- The DIRE funds XCID, XCIS and XSPI are typed `stock/common` with sector `Undefined` (ERRORS D30, OPEN; Part A A1.4).

## 1.5 Stage 2: terminal-publisher

The existing publisher is described in `BACKTEST_END_TO_END.md` section 4. What matters for any new file:

- **Deterministic bytes (FACT).** `encode` (`publisher.py:153-156`) writes compact JSON with `allow_nan=False`, then
  gzip level 9 with `mtime=0`; equal rows give equal bytes, and the sha256 is taken over the gzip bytes.
- **Columnar documents (FACT).** `columnar` (`publisher.py:149`) turns rows into `{column: [values]}`; readers decode
  with `decodeColumnar` and `inflateVerified` (`apps/edge-bff/backtest/src/core/datafile.ts:67, 91`), which require a
  `columns` list of equal-length arrays and check size and sha256.
- **Change detection by stamps (FACT).** A `daily` run republishes only what changed: price stamps per ticker-year
  (`PRICE_STAMPS_SQL`, `publisher.py:63`), event stamps per ticker (`EVENT_STAMPS_SQL`, `publisher.py:91`), broker by
  date (`Publisher.run`, `publisher.py:490`).
- **Write order (FACT).** Data files, packs, manifests, reference files, then `state.json` last
  (`publisher.py:549-554`), with `finished_at`. terminal-api and the backtest worker treat a new `finished_at` as a new
  publication.
- **Verify mode (FACT).** `verify` (`publisher.py:591`) compares every manifest-listed file with SQL (rows, first and
  last date, a column sum) and exits 1 on a mismatch.
- **OPEN (ERRORS M250).** Per-ticker files are overwritten under fixed keys during a run; the user chose
  content-addressed keys as the fix (2026-10-27).

**The xsection file family (PROPOSED, report 6.5).** Each whole-universe file:

| Rule | Content |
|---|---|
| Key | `v1/xsection/<name>.<sha16>.json.gz`: content-addressed (the first 16 hex of its sha256), never overwritten: the M250 content keys (`content_key`, `store`), as for every data file and pack |
| Body | one columnar document from `encode`: `schema_version`, `dataset`, `as_of`, `units`, `columns`, equal-length arrays; a row order stated in the document (for `price`: ticker, then date) |
| Index | `state.json` gains `xsection: {name: {key, sha256, bytes, rows, as_of}}`, still written last |
| Rebuild | each mode rebuilds the files whose inputs it changed (`daily`, `backfill`, `packs`: `price` and `actions`; `events`: `actions`; Phase 2 `daily`, `backfill`, `broker-range`: the flow files) and carries the other index entries forward unchanged. The publisher work in progress keeps this as one table, `XSECTION_REBUILT_BY` (name → modes); a new file adds its row there. A file that fails to build keeps its previous index entry |
| Cleanup | the publisher's `collect_garbage` (ERRORS M250, the same cleanup as for data files and packs): a daily run, before it writes, deletes an xsection object the `state.json` index no longer names, once the last finished run is an hour old (nothing newer than `state.json`; nothing while no index names a file), so a reader holding the previous index keeps its file for at least that hour (BACKTEST_END_TO_END.md 4.3) |
| Tests | a publisher unit test: each ticker's slice of `price` equals its pack document; the index is written before `state.json`; carry-forward; the cleanup keeps what the index names, waits the hour and keeps objects newer than `state.json`; (Phase 2) the completeness gate |

Phase 1 files: `price` (every ticker including IHSG, full history, columns `t,d,o,h,l,c,v`, plus
`tickers: [{t, pack_sha256, first, last, rows}]`) and `actions` (price-affecting actions with an ex-date on or after
2026-09-12, future ones included, with `ratio_old`, `ratio_new`; cash dividends of the last 6 years). Phase 2 files:
`broker_window` (raw F05 rows of the last 41 complete sessions, in the broker encoding `d,b,i,m,bv,sv,bl,sl`, plus
`buy_freq`, `sell_freq`) and a long all-board flow series; their final shape follows the flow indicators the user picks
(FLOW INDICATOR PROPOSALS 16.9).

## 1.6 Stage 3: terminal-api

The only holder of the bucket key. See `BACKTEST_END_TO_END.md` section 6 for its routes, cache and quotas.

| Route | Status | Answer | Quota, audit |
|---|---|---|---|
| `GET /api/terminal/v1/state` | FACT on `main` (EXEC-BACKTEST-LOAD); `apps/terminal-api/app/main.py:316` (`publication`) at `9a6cddc` | `finished_at`, `price_through`, `broker_through`, `broker_behind_sessions`: the fields of `STATE_FIELDS` (`apps/terminal-api/app/bucket.py:10`) | none |
| same, plus `xsection` | BRANCH (`9a6cddc`): `xsection` joined `STATE_FIELDS`; `Bucket.state` passes it through `xsection_index` (`bucket.py:21`) | the index, well-formed entries only | none |
| `POST /api/terminal/v1/xsection {names}` | BRANCH (`9a6cddc`, `main.py:418`) | per name a presigned URL, `sha256`, `bytes`, `rows`, `as_of`; a name not in the index answers 404 `xsection_not_published` | proxy-key callers only (`gateway`, `main.py:190`); one audit row under the `REF` pseudo-ticker (`apps/terminal-api/app/quota.py:5`, as reference files are logged, `main.py:297-299`), dataset `xsection`; file quota = number of names; bytes counted |

Rules a new file must meet at terminal-api (BRANCH, `bucket.py:12-41`): the name matches `XSECTION_NAME`
(`^[a-z0-9][a-z0-9_-]{0,31}$`); the index entry has exactly `key`, `sha256` (64 hex), `bytes` (≥ 1), `rows` (≥ 0) and
`as_of` (a string of at most 64 characters, else null); the key is `v1/xsection/<name>.<16 hex>.json.gz`. An entry that
breaks a rule is dropped from `/state` and never presigned. A call asks at most 16 names (`MAX_XSECTION_NAMES`,
`main.py:38`).

Neither route is in edge-bff's browser allow-list (`TERMINAL_ROUTES`, `apps/edge-bff/app/main.py:34-36`), so the browser
can never pull a whole-universe file. **A new xsection name needs no terminal-api code change**: names are validated
against the index, not against a list in code; only the size matters for the quota (section 1.15).

## 1.7 Stage 4: screener-worker (PROPOSED)

A private `node:http` service like the backtest worker: Node 22 with type stripping and the backtest worker's module
loader (`apps/backtest-worker/loader/register.mjs`, which resolves the Terminal's extensionless imports, ERRORS M249),
no npm runtime dependency, one replica in `sfo`, private network only, no Postgres or bucket credentials (report 6.4).
It reads the rack through terminal-api with the gateway proxy key, as the backtest worker does. Deployed from GitHub
`main` (DECIDED P3 a) with watch patterns over its own folder, the screener core, the backtest core, the terminal calc
folder, `indRegistry.json` and the borrowed backtest-worker files (report 6.4).

### 1.7.1 Refresh: one snapshot per publication

1. Poll `/state` every 60 s; act only on a new `finished_at`, one refresh at a time.
2. For each indexed file whose sha256 is in neither cache, ask `POST /xsection` for those names only, then download with
   `TerminalClient.file` (`apps/backtest-worker/src/terminal.ts:479`), which checks sha256 and size and fills the memory
   and disk caches. A cached file needs no grant. `/state` and `/xsection` are called by a thin client of the worker's
   own (`refresh.ts`), because `TerminalClient.api` is private (`terminal.ts:414`) and changing `terminal.ts` would
   change the Backtest's `engine_version`.
3. Decode each ticker through `priceSeries` (`datafile.ts:139`), so the Terminal and Backtest row rules apply unchanged.
4. Cross-check each ticker against its `/manifest` (last bar and row count).
5. Build the next snapshot on a builder thread; swap all-or-nothing. Any integrity failure keeps the previous version,
   logs `REFRESH_FAILED` and retries with backoff. When the new index names exactly the files already held, keep the
   snapshot and advance `published_at` only (MULTI-USER SCALE AND COST 6d.2).

### 1.7.2 The snapshot: defaults computed once, custom parameters on demand

One function, `series(id, params, output)` (report 6.7), keyed by (`price_data_version`, `screener_engine_version`,
`id`, `canonicalJson(resolveParams(BY_ID[id], params))`, `output`). On a miss it runs `Calc.out` on the ticker's
**full** history (tails are not exact for recursive and cumulative indicators: EMA 200 is up to 7.7% off with a 500-bar
tail, report 6.5) and keeps a tail of `SCREENER_WITHIN_MAX` + 1 bars. "Precomputed" and "dynamic" are the same call made
at two times, so they cannot differ; each cell says which it was (`source: precomputed | dynamic`).

Pre-warmed at each publication: all 53 indicators at registry defaults (76 outputs; about 67 MB of tails; 8.1-10.2 s on
one thread, FACT from the audit benchmark), every configuration a preset uses, the declared derived series, universe
attributes (last close, 1D %, ADV20 = `liquidity()`, `apps/edge-bff/backtest/src/core/signals.ts:174`, first and last
bar, bar count), the P4 remark data, default cross-sectional ranks, and every preset's match and near counts and full
result. Custom parameters are computed only for the tickers the planner keeps, and cached in a series LRU bounded by
`SCREENER_CACHE_BYTES`.

Never offered: raw level thresholds on cumulative indicators (OBV, PVT, A/D, NVI, PVI: the level depends on the first
bar forever); lengths above the derived caps; past evaluation dates (report 6.13).

### 1.7.3 The condition engine

Metric references (wire grammar, `contract.ts` `MetricRef`): `indicator`, `price`, `transform` (`pct_distance`,
`band_position`, `lag`, `change`, `rolling_max`, `rolling_min`, `rising_run`, `ma`, `ratio`, `vs_index`), `pattern`
(`breakout`, `breakdown`, `volspike`, `macross`, `macd_divergence`, `squeeze`, `stoch_cross_in_zone`, `new_high`,
`silent`), `flow` (Phase 2), `xsection` (`return_rank`), `universe`. These lists are data, read from the generated
catalogs, never kept in code (section 1.11).

| Test | Rule |
|---|---|
| VALUE | the metric at the evaluation bar; `gt`/`lt` strict; `between` inclusive and counted as one condition; `value > value2` refused, never reordered |
| STATE | `compare(lhs, op, rhs)[at]` (`apps/edge-bff/backtest/src/core/conditions.ts:52`); lhs and rhs from price, an output, a value or a second instance (SMA 50 vs SMA 200) |
| EVENT | a cross (bar 0 never true, NaN false, both sides finite on the previous bar) or a pattern signal within the last `within` bars (1 to 130); returns `event_date`, `bars_ago` on the ticker's own bars |

NA reasons (per cell, never failing the whole screen; `contract.ts` `NaReason`): `INSUFFICIENT_HISTORY`,
`NULL_AT_EVALUATION`, `FLOW_UNAVAILABLE`, `FLOW_LAGGED`, `NOT_APPLICABLE`, `DATA_INTEGRITY`, `MIXED_ADJUSTMENT_BASIS`.
Remarks explain a value and never change PASS, FAIL or NA: `STALE` and `PRICE_BREAK` per row, `PRICE_BREAK_IN_LOOKBACK`
per cell (P4, P4.1 A).

**As-of policy.** The evaluation date E is `price_through`. Each ticker is evaluated at its own last bar on or before E;
a ticker whose last bar is before E is STALE (hidden by default). `bars_ago` counts the ticker's own bars.

**Match and near.** `need = entryNeed(logic, at_least, active)` (`conditions.ts:263`); `met` counts PASS only;
`near = !match && need >= 2 && met == need - 1`, one rule for table, preview and CSV.

**Cross-section.** `rs_rank` ranks over a fixed population (active, non-stale stocks without a price break, finite value
at E), fixed before any condition, so showing a hidden ticker moves no other rank (P7).

### 1.7.4 The planner

| Stage | Evaluates |
|---|---|
| S0 | universe hard filters (type, sector and industry, price, ADV, the P4 chips, history length, explicit tickers, universe metric filters): conjunctive, outside `met` |
| S1 | population-level cross-sectional values (never pruned) |
| S2 | snapshot lookups, O(1) per ticker |
| S3 | dynamic conditions, cheapest first by a cost model |
| S4 | completion of every remaining cell of each survivor |

Pruning: θ = need − 1 when need ≥ 2, else need; a ticker with m passes and r unevaluated conditions is pruned iff m + r
< θ. It can never hide a match or a near miss (report 6.10, with its property test). ANY cannot be pruned. The worst
case is costed before running; above `SCREENER_MAX_CPU_MS` the request is refused (`LIMIT_EXCEEDED`, `compute_budget`,
naming the costliest condition), never cut short.

### 1.7.5 Private API

Header `x-screener-worker-key` (at least 32 characters) on every route except `/health`; private host only
(`contract.ts` `WORKER_ROUTES`): `GET /health`, `GET /ready` (200 only with a loaded snapshot), `GET /v1/catalog`,
`GET /v1/universe`, `POST /v1/run`, `/v1/preview`, `/v1/validate`, `/v1/counts`.

Logs are JSON with no secrets: one `refresh` line per publication (`data_version`, files, bytes, granted, cached,
timings, integrity failures, `orphans`, `snapshot_digest`, rss) and one `run` line per screen (stages, per-condition
source and cache, `cpu_ms`, pruned, payload bytes).

## 1.8 Stage 5: edge-bff (PROPOSED; the module is being written)

`apps/edge-bff/app/screener.py`, mounted like the Backtest module (`apps/edge-bff/app/backtest.py`):

| Route under `/api/v1/screener/` | Auth | Worker route |
|---|---|---|
| `GET catalog`, `GET universe` | session | `GET /v1/catalog`, `/v1/universe` |
| `POST run`, `preview`, `validate`, `counts` | session + `Origin` + `X-CSRF-Token` | the same under `/v1/` |
| `GET items?kind=screen\|metric`, `PUT items/{item_id}`, `DELETE items/{item_id}` | session; writes with CSRF | `PUT` validates through `/v1/validate` first |
| `GET watchlist`, `PUT watchlist/{ticker}`, `DELETE watchlist/{ticker}` | session; writes with CSRF | — |

- **Relay as bytes.** `run`, `preview` and `counts` are passed through as gzip bytes; edge-bff parses only error bodies
  (6d.5).
- **Catalog and universe** are kept in memory keyed by (`price_data`, `screener_registry`), refreshed when the worker's
  `/health` shows other versions (checked at most every 60 s) or when any worker answer carries a newer `price_data`;
  answered with `ETag` = sha256 of the bytes and `304` on `If-None-Match` (API CONTRACT 8.4).
- **Latest wins** per (`owner_key`, page) through `client_order {page, seq}`; an older call answers 409
  `SCREEN_REPLACED` or `PREVIEW_REPLACED`.
- **Settings:** the pair `SCREENER_WORKER_URL` / `SCREENER_WORKER_KEY` (key at least 32 characters, a private host
  outside `local`, the pattern of `apps/edge-bff/app/config.py`); off (503 `SCREENER_DISABLED`) when the URL is empty.
- **A new metric needs no edge-bff change:** the catalog is relayed as the worker built it.

## 1.9 Stage 6: the page and its load sequence (PROPOSED)

A 1:1 port of the user's prototype (`screener EDGE layout.html`), module by module, under `apps/edge-bff/screener/`
(BRANCH: the scaffold at `8a236eb`, first modules at `9a6cddc`). Words of the app live in `src/texts.ts` (BRANCH); words
of the EDGE shell in `apps/edge-bff/static/edge-labels.js` (AGENTS.md). The page holds no formula code and downloads no
rack file; its CSP is `connect-src 'self'`.

Load sequence (PAGE LOAD SEQUENCE 6c.4; the Terminal and Backtest pattern):

| Step | What happens |
|---|---|
| S1 | the frame paints its whole layout from static markup, each data area with the shared loading ring (`apps/edge-bff/terminal/src/ui/spin.ts`); controls that need the catalog are visibly inactive |
| S2 | `boot()` sends at once: session (CSRF), `GET catalog`, `GET universe` (each with `If-None-Match` when the page has a cached copy), `GET items?kind=screen`, `GET watchlist` |
| S3 | on the first authenticated answer, the page draws the cached catalog, universe and last result from IndexedDB (`rack.ts` `fileCache()`, keyed by sha256), marked "Updating…" (P24, PROPOSED) |
| S4 | `304`: the cache is current; `200`: the new bytes replace the drawing |
| S5 | an empty screen needs no run (its rows are the universe after `universe.ts`, the same function the worker runs in S0); a remembered screen whose cached result has the current versions needs no run either; otherwise `POST run` |
| S6-S8 | saved screens and watchlist fill in when they answer; the preview, "Stock vs IHSG", counts of saved screens and Send to Backtest wait until asked; edits are debounced 350 ms and the previous run is aborted |

Targets (P28, PROPOSED): frame first paint ≤ 1.4 s cold, first results of an empty screen ≤ 1.8 s cold, no main-thread
task over 50 ms.

**Disabled with a reason.** A metric whose availability is not `AVAILABLE` is shown, disabled, with the reason the
catalog gives (`REQUIRES_DATA`, `REQUIRES_DECISION`, `NOT_APPLICABLE`). A preset is enabled only when all its legs are
available; it never runs with a leg removed.

## 1.10 The indicator contract

```
 workbook Technical_Indicators_53_Frontend_Display_Spec.xlsx (user upload, not committed)
        │ hand-kept copy
        ▼
 apps/edge-bff/terminal/src/data/indRegistry.json  (53 rows: id, key, name, req, outs, params with def/min/max/opts)
 apps/edge-bff/terminal/src/calc/indicators.ts      (F: the formulas; DEFAULTS: the executable defaults)
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
        │ served through GET /v1/catalog                                                 PROPOSED
        ▼
 the page's builder (no XPARAM copy in the page)
```

- **FACT.** `build-registry.mjs` accepts a parameter only when `DEFAULTS` has it, takes the module's default, and
  records the others under `not_accepted` with a reason (`build`, `build-registry.mjs:28-58`); it throws when a registry
  row has no function in `F` or `DEFAULTS` has a key the registry lacks. `npm run registry:check` fails on a stale file;
  the backtest worker exits at start when the artifact does not match its sources (`version.ts:37-41`,
  `server.ts:348-349`).
- **The approved formula contract (FACT, user 2026-10-25).** "Yang ada kita sesuaikan saja dengan feature 4, tapi jika
  tidak ada kita pakai HTML": an indicator Feature 04 stores follows Feature 04 (TA-Lib seeds); the others follow the
  Terminal reference engine. Verified in `apps/edge-bff/terminal/tests/calc/PARITY.md`.
  `scripts/terminal_indicator_spec.py` holds the specification of every indicator (`I`, line 31) and generates
  `verification/terminal_api/INDICATOR_SPEC.md` and the applied migration `20261025_102_terminal_indicator_formulas.sql`
  (the AI's `AI_formula_reference` rows CALC_201 onward, `FIRST_ID`, line 22); its `--check` proves both unchanged.
- **The screener registry (BRANCH at `9a6cddc`; report 6.8).** The overlay holds only product choices: `shape`, the
  allowed test forms per output with the prototype's operators and labels, search synonyms, the default card, the
  provisional cost model of the caps (P5), and explicit overrides that each name their evidence (one known: I09
  `factor > 0`). The generator derives, by running `F`: `first_valid_bar` per output; `history_class` (window,
  recursive, cumulative, calendar) by a cut probe; display unit and `level_comparable` by a scaling probe;
  `price_compare_lag` by a lag probe (Donchian upper reads the previous bar); `inputs` per source by a poison probe;
  narrowing (an exclusive minimum where the output degenerates; integer-only where `F` floors the value; parameters
  `not_accepted` as "not read by the calculation module" hidden); `cost_class`; caps; the Feature 04 oracle mapping read
  from `scripts/terminal_indicator_spec.py --json`.
- **Narrow-only.** The overlay and the derived narrowing may only narrow the base registry, so every transferable
  screener condition is also valid for the Backtest.
- **Checks.** `--check` re-derives every field and fails on a difference; the worker refuses to start on a hash mismatch
  and runs the backtest worker's own registry check; a test requires one overlay entry per base id and vice versa (TEST
  PLAN 10b.10).

## 1.11 The non-indicator metric catalog and derived availability (PROPOSED)

Everything that is not one of the registry indicators (transforms, patterns, cross-sectional ranks, universe attributes,
flow metrics, fundamentals, later macro series) is described as **data** in
`apps/edge-bff/screener/src/core/screener-metrics.json`, checked by the generator like the registry (report 6.12). Each
entry carries:

| Field | Meaning |
|---|---|
| `id`, `group`, `kind` | identity; `kind` is one of the wire kinds of section 1.7.3 |
| `params` | each with type, default, min, max (flow maxima derived from the published window) |
| `tests` | the test kinds it allows (VALUE, STATE, EVENT) |
| `unit` | raw unit on the wire (IDR, percent, fraction, sessions, …) |
| `requires {file, columns}` | the xsection file and columns it needs |
| `applies_to` | a predicate over universe attributes (for example `Industry = Banks`); outside it the cell is `NOT_APPLICABLE` |
| `formula`, `interpretation`, `misuse`, `evidence` | the `Feature_Catalog` fields, so a later AI onboarding can reuse them |

Plus a `periods` block: 1M, 3M, 6M, 1Y = 21, 63, 126, 252 sessions (P23 a).

**Availability is derived at run time**: a metric is `AVAILABLE` when every file and column it `requires` is in the
`state.json` index; else `REQUIRES_DATA`; `REQUIRES_DECISION` when a user decision is open; `NOT_APPLICABLE` by
`applies_to`. Nothing is enumerated in the page or in validation code. Consequence for onboarding: **a new metric of an
existing kind becomes available by adding catalog entries and publishing its file; it needs code only when its
computation is new** (section 2.1).

## 1.12 Feature 04's role

DECIDED (P2 a, 2026-10-28): Feature 04 is unchanged (no column, version, checkpoint, worker or migration change) and is
not read at run time. It keeps three roles:

1. **Parity oracle in tests.** The snapshot is compared with Feature 04 on every equity ticker at a common date for the
   registry-default columns (`sma_20`, the three MACD columns, `rsi_14`, the three Bollinger columns, `atr_14`,
   `adx_14`) and five exact derivations (I28 %B, I29 bandwidth, I31 NATR, I32 stddev, I25 PPO line); the configurations
   Feature 04 stores at other parameters (`sma_50`, `ema_12`, `ema_26`, `ema_50`, `ema_200`) are reached through the
   dynamic path; Feature 01 is the oracle for I35, I37 and I17. Pass: relative difference ≤ 1e-12 and identical nulls
   (FACT today: max 1.16e-15). Pinned in `verification/screener/F04_PARITY.md` with `registry_version` and the Feature
   04 version string (PROPOSED). The mapping is the `ORACLE` table of `scripts/terminal_indicator_spec.py --json`
   (BRANCH, `9a6cddc`); its `oracle_problems` check refuses an oracle column missing from the row's human-readable
   `feature04` text.
2. **Optional reconciliation file** (Phase 2, needs a SELECT grant on Feature 04 in migration 2).
3. **AI consumer**, unchanged.

Why not a run-time source (report 6.6): no precision gain, 9 of 53 indicators fully covered, a second time base (Feature
04 finishes at about 10:09 UTC, the rack at about 13:03 UTC), coupling to its repair state, and no grant.

## 1.13 Versions

| Version | What it hashes | Changes when | Where it shows |
|---|---|---|---|
| `price_data` | `dataVersion` (`datafile.ts:271`) over (ticker, `price`, pack sha256) of every ticker | a publication changes any price | every answer `versions`; cache keys |
| `flow_data` | the same over the flow files | Phase 2 | every answer (null before) |
| `registry` | `registry_version` of `backtest-registry.json`, passed through | `indRegistry.json` or `indicators.ts` changes (a registry release) | every answer |
| `screener_registry` | sha256(base registry + overlay + derived fields)[:16] | the overlay, the base or a probe result changes | every answer; saved items |
| `screener_engine` | content hash of screener core, the worker's `src`, the imported core and calc files, and the Node major (the `version.ts` mechanism) | any of that code changes | every answer; cache keys |
| `definition_hash` | sha256 of `canonicalJson` of the definition, parameters resolved, labels removed | the screen changes | run and counts; result cache; saved items |
| Backtest `engine_version` | every file of `backtest/src/core` and `apps/backtest-worker/src` | **must not change during the Screener build** (tripwire) | Backtest results |

A saved screen whose parameter left the registry range after a release is shown "needs review" with the field; nothing
is adjusted (API CONTRACT 8.7). A new data family adds its own data version beside `price_data` (as `flow_data` does).

## 1.14 Caches

| Where | What | Key | Lifetime |
|---|---|---|---|
| terminal-api process | manifests, the state | ticker; `finished_at` | until the next publication (checked every 60 s) |
| Worker memory | snapshot: defaults, tails, attributes, ranks, preset counts and results | `price_data` + `screener_engine` | until the next publication (PROPOSED: the previous one kept 600 s as a grace window, 6d.4) |
| Worker memory | series LRU (custom parameters) | (`price_data`, `screener_engine`, id, canonical params, output) | swap; `SCREENER_CACHE_BYTES` |
| Worker memory | result cache (gzip bytes) | (`price_data`, `screener_engine`, `screener_registry`, `definition_hash`) | swap |
| Worker disk | verified gzip files | sha256 | LRU in `SCREENER_CACHE_DIR` (no volume) |
| edge-bff memory | catalog, universe bytes and their `ETag` | (`price_data`, `screener_registry`) | a newer version on `/health` or in any answer |
| Browser IndexedDB `terminal-files` | last catalog, universe and result bytes | sha256 (= `ETag`), pointer `localStorage scr.boot` | shared 50 MB LRU (`rack.ts` `CACHE_LIMIT`) |
| `edge_bff` tables | saved items, watchlist | `owner_key` | never cached |

Every byte cache is keyed by content or by version, so a new publication never serves stale numbers.

## 1.15 Limits (provisional, P5; replaced by the Phase 17 measurements)

Every worker limit is an environment variable **with no default**: the service does not start without it (backtest
worker convention). Each limit is published in the catalog with its rule, how to pass it, one right and one wrong
example (AGENTS.md "Gates and evidence").

| Limit | Initial value | Variable |
|---|---|---|
| Active conditions | 20 | `SCREENER_MAX_CONDITIONS` |
| Universe metric filters | 8 | `SCREENER_MAX_METRIC_FILTERS` |
| `within` (technical) | 130 sessions; the snapshot tail is this + 1 | `SCREENER_WITHIN_MAX` |
| Indicator lengths | derived cap per parameter | `SCREENER_CAP_BUDGET_MS` |
| Compute budget, deadline | cost model; 20 s | `SCREENER_MAX_CPU_MS`, `SCREENER_DEADLINE_MS` |
| Queue | 4 | `SCREENER_QUEUE` |
| Counts request | 50 definitions | `SCREENER_MAX_COUNTS` |
| Response | ≤ 2 MB JSON | `SCREENER_MAX_RESPONSE_BYTES` |
| One xsection file (gzip), inflated, one refresh | 2 × the first measurement | `SCREENER_MAX_FILE_BYTES`, `SCREENER_MAX_INFLATED_BYTES`, `SCREENER_MAX_REFRESH_BYTES` |
| Saved items, watchlist | ≤ 500 each (the `PIN_LIMIT` precedent, `apps/edge-bff/app/store.py:320`) | `SCREEN_LIMIT`, `WATCHLIST_LIMIT` |
| terminal-api default quota (one shared gateway subscriber) | `files_per_hour` 60, `megabytes_per_day` 300 (`database/migrations/20261025_100_create_terminal_schema.sql:79-83`); overridden to 1e9 on dev, TEMPORARY (decision U1) | `terminal.quota` |

**Onboarding consequence:** a new file must fit `SCREENER_MAX_FILE_BYTES`, `SCREENER_MAX_INFLATED_BYTES` and
`SCREENER_MAX_REFRESH_BYTES`, and its daily bytes the shared `megabytes_per_day` (section 2.3, L2).

## 1.16 Multi-user notes

The user's requirement (2026-10-28): "ini nanti akan multiuser, jadi infrastruktur harus bisa di scale UP + efficient
cost wise". The design (MULTI-USER SCALE AND COST 6d, PROPOSED):

- **Shared, once per publication:** bars, the 53 defaults, universe attributes, ranks, preset counts and results,
  catalog and universe bytes. A run answer is a function of (publication, versions, definition) only and carries no
  owner, so two users with the same screen share one computation (a test asserts byte-identical answers for two owners).
- **Per user:** session, saved items, watchlist (all keyed by `owner_key`), one run and one preview in flight per page.
- **Replicas are stateless.** A worker replica's whole state is a function of the publication and the engine version;
  any replica can answer any request. Capacity grows in this order: compute threads first (one copy of the bars), then
  replicas (each holds its own snapshot, about 0.4-0.7 GB steady, INFERENCE).
- **Version skew across replicas** is handled by pinning (`data_version` on run, counts and preview), a grace window for
  the previous snapshot, and 409 `DATA_VERSION_PENDING` for a replica that has not swapped yet.
- **Fairness:** per-owner lanes in the worker (an opaque owner tag), round-robin scheduling, a bounded queue.
- **terminal-api traffic does not grow with users**: per replica and publication, one grant for 2-4 files.
- **Onboarding consequence:** a new dataset adds to every replica's memory and start time. Measure the inflated size and
  the snapshot time, and record them (section 2.3, L5).

## 1.17 Send to Backtest (Phase 1b, PROPOSED)

`apps/edge-bff/screener/src/core/to-backtest.ts` translates a screen into Backtest cards with an explicit lossless or
lossy classification, using the Backtest catalog's own `limits` (`max_portfolio_tickers`, `window_bars`,
`max_conditions`). Lossless today: registry-indicator conditions `gt`, `lt`, crosses (same instance), Supertrend/PSAR
direction, core patterns, Donchian prior band as `breakout`, all-board `fnet`, `broker`, `top5`
(`conditions.ts:194-198`, `FLOW`), and ADV as `min_avg_value_20d_idr`. Everything else goes to `left_out` with a reason
and travels in the handoff's full `definition`, so a later Backtest release can adopt it. The handoff is a one-shot
`sessionStorage['edge-backtest-import']` plus a `postMessage` navigation; the Backtest change is page-only (`app.ts`,
new `import.ts`).

## 1.18 Security

Never in the browser: database URLs, bucket credentials, `TERMINAL_PROXY_KEY`, `SCREENER_WORKER_KEY`, internal hosts.
`/state` and `/xsection` are outside the browser allow-list; `/xsection` accepts only the proxy key. The worker holds no
database or bucket credential. Presigned URLs and keys are never logged. Every edge-bff store statement filters
`owner_key`; every write goes through the CSRF dependency.

## 1.19 Operations

- **Environment:** one Railway environment, `dev`. Deploy outside 00:00-01:00 and 12:00-13:05 UTC (the publisher's runs,
  ERRORS M250). Claim a deployment only at the exact deployment's `SUCCESS` (AGENTS.md).
- **Deploy sources:** screener-worker and edge-bff from GitHub `main` (after each merge check that the merge commit was
  deployed, ERRORS M252); terminal-api and terminal-publisher by CLI upload under the ERRORS M248 procedure (merge
  first, deploy the merge commit; the last upload wins); a manual publisher run follows ERRORS M229 (clear the cron,
  `railway up`, restore).
- **New Railway resources** (the screener-worker service) are created through a pinned, reviewed IaC plan
  (`railway config pull --force`, `railway config plan --out`, apply only when the plan holds exactly the intended
  changes; ERRORS R29, R41, R42; report 6.17).
- **Tests per part** (one suite at a time):

  | Part | Command (from the folder) | Status |
  |---|---|---|
  | publisher | `python -m pytest apps/terminal-publisher/tests` | FACT |
  | terminal-api | `python -m pytest -q` in `apps/terminal-api` | FACT |
  | Terminal formulas | `npx vitest run tests/calc` in `apps/edge-bff/terminal` | FACT |
  | backtest worker | `npm test`, `npm run registry:check` in `apps/backtest-worker` | FACT |
  | indicator spec | `python3 scripts/terminal_indicator_spec.py --check` | FACT |
  | screener registry | `npm run registry:check` in `apps/edge-bff/screener` (needs python3 for the oracle) | BRANCH |
  | screener core and page | `npm test` (vitest), `npm run typecheck` in `apps/edge-bff/screener` | BRANCH / PROPOSED |
  | screener-worker | `npm test` in `apps/screener-worker` | PROPOSED |
  | edge-bff | `EDGE_TEST_POSTGRES_URL=<disposable Postgres> python -m pytest -q` in `apps/edge-bff` (`tests/test_screener.py`) | PROPOSED |
  | tripwire | `npm run tripwire` in `apps/edge-bff/screener` (`scripts/screener/check_backtest_untouched.mjs`; its tests: `node --test scripts/screener/check_backtest_untouched.test.mjs`) | BRANCH |
  | Feature 04 parity | `scripts/screener/parity_f04.py`, record in `verification/screener/F04_PARITY.md` | PROPOSED |

## 1.20 Open and temporary items that affect onboarding

| Item | Status | Where |
|---|---|---|
| Mixed adjusted/raw price history; the Screener's price-break remark | OPEN; the remark is TEMPORARY until the data-layer fix | ERRORS D22; report 6.12 |
| Per-ticker files overwritten in place during a publisher run | OPEN; xsection files are content-addressed from the start | ERRORS M250 |
| Broker data lags prices | OPEN | ERRORS M243; P10 |
| No delisted tickers, no historical membership or sector history before 2026-09-28 | no point-in-time screens; history is "today only" | APPENDIX C.6 |
| One shared gateway account with an unlimited quota override | TEMPORARY | decision U1 |
| Registry defects behind the screener narrowing (I09 factor 0, I37 label, Donchian same-bar test, `annualization_periods` floor) | OPEN for the Backtest; TEMPORARY screener-only narrowing until the registry release | ERRORS M255-M258; P6 |
| `topNAccumulation` copied in screener core because `flow.ts` is in the Backtest's engine hash | TEMPORARY; a test pins `flow.ts`'s hash | report 6.11 |
| Flow decisions P9 (bandar), P10 (lag), P20 (calendars, default broker), D1-D14 | OPEN, before Phase 2 | FLOW INDICATOR PROPOSALS 16.11 |
| Fundamentals, market cap, index membership, board, notation, free float | no data; shown disabled with reasons (P11) | APPENDIX C; EXEC-MCAP waits for its go |

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
   change only in their own approved release (2.4).

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
| L4 registry / metric catalog / contract | yes (registry) | yes (`screener-metrics.json`) | yes | yes (+ a wire kind the first time) | yes (+ a wire kind the first time) | yes |
| L5 screener-worker | regenerate only | code in screener core | decoder + metrics | decoder + as-of | decoder + alignment | decoder + S0 filter |
| L6 edge-bff | no | no | no | no | no | no |
| L7 page | texts only (generic builder) | texts | texts | texts, "period X, published Y" | texts | texts, filter control |
| L8 Backtest | the same release | optional, later | optional, later | screen only | optional, later | screen only |
| L9 AI exposure | AI formula row | no | optional onboarding | optional onboarding | optional onboarding | optional onboarding |

Notes: "no" for terminal-api rests on `/xsection` validating names against the index (BRANCH, section 1.6). "A wire kind
the first time" means the first fundamental and the first macro series each need one new reference kind in `contract.ts`
(worked examples 2.13 and 2.14); later entries of the same kind are data only.

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
| File name matching terminal-api's `XSECTION_NAME` (`^[a-z0-9][a-z0-9_-]{0,31}$`; section 1.6) and its document: `schema_version`, `dataset`, `as_of`, `units` per column, `columns`, row order stated | the document builder and its test |
| Its row in the publisher's rebuild table (`XSECTION_REBUILT_BY`, work in progress): which modes rebuild it | a test per mode |
| One bounded SQL statement (or one per date with literal bounds) through the read-only login; measured | `EXPLAIN (ANALYZE, BUFFERS)` in `DATABASE_CHANGELOG.md` |
| Deterministic bytes: built with `encode`; values as stored (no rounding, no adjustment); `allow_nan=False` passes | a test: the same rows give the same sha256 |
| Content-addressed key and index entry `{key, sha256, bytes, rows, as_of}` in `state.json`, written before `state.json` | a test of the write order |
| Change detection: a stamp so `daily` rebuilds the file only when its inputs changed; otherwise the index entry is carried forward | a test: an unchanged source uploads nothing |
| Completeness gate for data written in rounds (a date is published only when it is complete for every ticker) | a fixture with a partial date |
| `as_of` meaning stated (last complete date; for macro the last value available at the cut time) | the document and the catalog entry |
| Verify mode extended: the file against SQL (rows, first and last date, a column sum) | `publisher.py verify`; a test |
| Size: gzip and inflated bytes measured at the first run; fits the worker caps and the daily quota | the `done` log line; `RAILWAY_CHANGELOG.md` |
| Orphans (rows whose ticker is not in the reference file) counted and logged, never named in code | the log line |
| Publisher tests green; backfill then daily uploads nothing new | `python -m pytest apps/terminal-publisher/tests` |

**L3 — terminal-api**

| Check | Evidence |
|---|---|
| No code change needed: `/xsection` validates names against the index (BRANCH, `xsection_index`). Check the entry passes its rules (name, five fields, key pattern) or it is silently dropped from `/state`; and that the total names per publication stay within `MAX_XSECTION_NAMES` (16) per call. If a change is needed, follow M248 for the CLI deploy and keep `/state`'s existing tests | `apps/terminal-api/tests/test_api.py` |
| Quota: grants per day × bytes fit `files_per_hour` and `megabytes_per_day` of the shared subscriber without the TEMPORARY override (6d.7) | arithmetic in the change record |

**L4 — Contract, registry and metric catalog**

| Check | Evidence |
|---|---|
| Indicators (registry release only): base registry regenerated (`npm run registry` in `apps/backtest-worker`), overlay entry (shape, tests, synonyms, default card, labels), screener registry regenerated (`npm run registry` in `apps/edge-bff/screener`), both `registry:check` green | the generated files |
| Other metrics: `screener-metrics.json` entries with `id`, `group`, `kind`, `params` (ranges; maxima derived from the published window), `tests`, `unit`, `requires {file, columns}`, `applies_to`, `formula`, `interpretation`, `misuse`, `evidence` | the generator's check |
| Availability derived, never coded: removing the file from a fixture index makes the metric `REQUIRES_DATA` with no code change | `tests/core/metrics.test.ts` (PROPOSED) |
| A new wire kind or NA reason added to `contract.ts` only when no existing one fits; each new refusal or NA meets the four "Gates and evidence" items (rule seen first, how to pass, right and wrong example, a message naming the field and the fix) | `contract.ts`; texts |
| Defaults, ranges and thresholds are the user's words, recorded; thresholds never validated against returns are labelled so | `EXEC.md` |
| Presets that use the metric: `presets.json` entries; a preset is enabled only when all its legs are available | the catalog test |

**L5 — screener-worker**

| Check | Evidence |
|---|---|
| Refresh: the file is granted only when not cached, downloaded with sha256 and size checks, decoded with the shared decoders (`decodeColumnar`/`inflateVerified`) | refresh tests |
| Cross-checks on load (counts, dates, a self-check against a stored oracle where one exists); a failure keeps the previous snapshot and logs `REFRESH_FAILED` | a fixture with a corrupted sha256 |
| Units converted once, at the decoder, from the document's `units`; raw units on the wire | a unit test |
| Alignment: the as-of rule for each cell (own bars, market sessions, or backward as-of on availability) and the `eval_date` each cell reports | a fixture across a holiday |
| Its data version (as `flow_data`) enters `versions` and the cache keys | a version test |
| Memory and start time measured with the new file (refresh log `rss`, `defaults_ms`) | `verification/screener/BENCHMARK.md` |
| Tripwire green: no Backtest formula or core file changed, the Backtest worker as its recorded baseline approves | `check_backtest_untouched.mjs` |

**L6 — edge-bff:** nothing for a new metric (the catalog is relayed). A new route or setting only with its tests in
`apps/edge-bff/tests/test_screener.py`.

**L7 — Page**

| Check | Evidence |
|---|---|
| Labels and reasons worded in `apps/edge-bff/screener/src/texts.ts` from codes (no message from the server); shell words in `static/edge-labels.js` | the texts test |
| Disabled-with-reason states for `REQUIRES_DATA`, `REQUIRES_DECISION`, `NOT_APPLICABLE`; nothing hidden silently | page tests |
| Units formatted from the catalog `unit` (Rp B, %, sessions) | page tests |
| No formula and no rack download in the page bundle | the bundle test |

**L8 — Backtest (optional, later):** see 2.9.

**L9 — AI exposure (optional, separate):** see 2.10.

**L10 — Tests:** each layer's suite (section 1.19), plus the class-specific tests in 2.4 to 2.8.

**L11 — Records** (AGENTS.md step 5), in the same task:

| Record | When |
|---|---|
| `DATABASE_CHANGELOG.md`, `DATABASE_SCHEMA.md`, `APPLIED.sha256` | a migration or a data load |
| `RAILWAY_CHANGELOG.md`, `.railway/railway.ts` (then `railway config pull --force`, `railway config plan`) | a deploy, a variable, a service |
| `ERRORS_AND_SOLUTIONS.md` (Part D format; Part A when a lesson changes how data must be shaped) | anything found |
| `BACKTEST_END_TO_END.md`, `apps/edge-bff/backtest/CONTRACT.md` | the publisher's or terminal-api's Backtest-facing behaviour changes, or a Backtest release |
| `UPDATE_TABLE.md` | a manual refresh of a source now has a rack step (flow) |
| `AI_TOOLS.md`, `NEW_TABLE_ONBOARDING_PLAN.md` steps, `DATABASE_INDEX_ACCEPTANCE.md` | the AI reads the table |
| this document | every onboarding: add the metric to Part 1 where it changes the flow; add a lesson to Part 2 |
| `EXEC.md` / `PLAN.md` | approval with the user's words; removal when done |

**L12 — Deploy order (PROPOSED, generic):**

1. Migration (DRYRUN, APPLY, read back) and the loader; the source rows verified.
2. screener-worker and the catalog entries (GitHub `main`): the new metric appears **disabled** (`REQUIRES_DATA`)
   because no file is indexed yet. Nothing breaks.
3. terminal-publisher (CLI, M248, outside the M250 windows): its next run writes the file and the index entry.
4. The worker's next refresh picks the file up and the metric turns `AVAILABLE` without another deploy.
5. Verify live: the refresh log line, a screen with the metric, the page. Claim each step only at `SUCCESS` and with the
   read-back.

The order works either way (the worker ignores an indexed name it does not know), but worker-first never shows an
enabled metric without data.

## 2.4 Class A: a technical indicator computed from OHLCV

- **Same indicator, other parameters:** nothing to onboard. The dynamic path computes it (section 1.7.2).
- **Arithmetic over existing outputs** (a distance, a ratio, a lag, a rolling extreme, a moving average of an output): a
  transform or pattern, written in screener core (`transforms.ts`, `evaluate.ts`) with its entry in
  `screener-metrics.json`. It is condition arithmetic over `F` outputs and the exported `sma`/`ema`/`rma`, never a new
  formula. Its result lags and units come from the same probes (a rolling maximum of the high reads the previous bar as
  the right side of a price comparison). `screener_engine` changes; the Backtest does not.
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
| History class and warm-up: recursive or cumulative outputs need full history; cumulative levels are not offered as raw thresholds | section 1.7.2 |
| Cost class and cap measured; caps derived from `SCREENER_CAP_BUDGET_MS` | the generator |

## 2.5 Class B: a flow or broker metric

Sources: `IDX_Broker_Summary` (raw, Stockbit) → Feature 05 (broker, investor type, board, date) → Feature 02 (rolling),
Feature 03 (stock, board, date), Feature 06 (foreign and domestic per board). Refreshed by `stockbit-updater` per token
(`UPDATE_TABLE.md`), not on a schedule. Phase 2 of the Screener; its decisions are open (P9, P10, P20, D1-D14).

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
| Copies of Backtest formulas | `topNAccumulation` lives in screener core with a test that N = 5 equals `top5Accumulation` (`flow.ts:108`) bitwise; a test pins `flow.ts`'s hash (TEMPORARY) |
| Grants | F06 or F03 through migration 2 (publisher's own group) |
| Self-check | per board, recomputed sums must equal the stored F06 rows where the ticker has the sessions; a mismatch marks flow `DATA_INTEGRITY` |
| Manual refreshes | after a manual F05/F06 refresh the rack keeps the old flow files until the next publisher run (`UPDATE_TABLE.md` gains that step, PROPOSED) |

Worked example 2.12.

## 2.6 Class C: a fundamental metric

FACT (APPENDIX C.1): no fundamental source exists in the system today. Of the prototype's 32 fundamental metrics none is
available, 2 are derivable (dividend yield and years of dividends, from `idx_event_annotation`), 25 need new data and 5
are bank-only. Fundamental presets ship disabled with reasons (P11).

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
| Do not add columns to `ref/tickers.json.gz` casually | FACT: every column after `type` becomes a Backtest portfolio grouping (`publish_refs`, `publisher.py:418-431`; CONTRACT decision PF6); a numeric column would appear as a grouping with every stock unclassified. A categorical attribute the Backtest should also group by may go there by decision; a numeric one goes into its own xsection file |
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
(`conditions.ts:194-198`), and within-N windows of 1 to 20 bars (`WINDOW_BARS`, `conditions.ts:259`).

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

Example: Ichimoku Cloud as I54. It is the one indicator the prototype uses that the 53 lack: the `ichimoku` legacy key
and the `ichi` preset are shipped disabled until a registry release (P6 a, decided with the go as the report
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
- `screener-overlay.json`: the I54 entry (shape, the test forms: close above or below the cloud, Tenkan crosses Kijun,
  the default card, synonyms "ichimoku", "cloud", "kumo", labels).
- `npm run registry` in `apps/edge-bff/screener` (`build-screener-registry.mjs`) derives the rest: `first_valid_bar`
  (INFERENCE: about 52 + 26 bars for the displaced Senkou B; the probe gives the exact number), `history_class`, units
  (price level, comparable with close), `price_compare_lag`, `inputs` (H, L, C), narrowing, cost class, caps. Then
  `npm run registry:check` green; the overlay coverage test (one overlay entry per base id) fails until this entry
  exists.
- `presets.json`: the `ichi` preset now has all legs; it becomes `AVAILABLE` by derivation.
- Feature 04 oracle: none (`ORACLE` has no I54 entry); say so with an `ORACLE_NOTES` line.

**Step 5 — tests across consumers.** Terminal calc tests; backtest worker `npm test` (its `registry.test.ts` and
`validate.test.ts` read the registry); Backtest page vitest and smoke; screener core tests (VALUE, STATE, EVENT on I54;
default = dynamic at default parameters bit for bit); the tripwire reports the expected `registry_version` change, which
the release record names.

**Step 6 — deploy (one release window, outside 00:00-01:00 and 12:00-13:05 UTC).**
1. Merge to `main`: edge-bff (Terminal and Backtest pages, Screener page) and screener-worker redeploy from GitHub
   (check the merge commit was deployed, M252).
2. Deploy the backtest worker from the merge commit by CLI (M248). INFERENCE: until it is live, the Backtest page offers
   I54 while the old worker refuses it; keep the window short and say so in the release record.
3. Read back: the worker's `/health` shows the new `registry` and `screener_registry`; the catalog lists I54; a screen
   with I54 and a Backtest run with I54 both work; the Terminal draws it.

**Step 7 — records.** `RAILWAY_CHANGELOG.md` (the three deployments at SUCCESS), `DATABASE_CHANGELOG.md` (the formula
row), `ERRORS_AND_SOLUTIONS.md` (anything found), `BACKTEST_END_TO_END.md` section 14 and `CONTRACT.md` if a rule
changed, this document, `EXEC.md`. Saved screens are unaffected (a release only adds an id).

## 2.12 Worked example 2: add a flow metric (FL10, net-buy concentration HHI)

From FLOW INDICATOR PROPOSALS 16.5: "whether the stock's net buying over D sessions is held by one or two brokers (near
1) or spread over many (near 0)". PROPOSED; the user picks the Phase 2 set (D1) and the HHI basis (D3: net-buy HHI
recommended).

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

**L4 catalog.** One `screener-metrics.json` entry, for example:

```
{ "id": "fl10_netbuy_hhi", "group": "flow.concentration", "kind": "flow",
  "params": [{"key": "window", "type": "integer", "default": 20, "min": 1, "max": 20},
             {"key": "board", "type": "enum", "default": "all", "options": ["all", "regular"]}],
  "tests": ["value"], "unit": "fraction",
  "requires": {"file": "broker_window", "columns": ["d", "b", "i", "m", "bv", "sv"]},
  "applies_to": null,
  "formula": "H = sum over brokers with n_b > 0 of (n_b / sum of positive n_b)^2;
              n_b = broker net over D sessions, both investor types, all boards",
  "interpretation": "Near 1: one or two brokers hold the net buying; near 0: spread over many.",
  "misuse": "Not market-structure thresholds (0.10/0.18); higher for illiquid stocks; says who holds
             the net buying, not how large it is (pair with FL09); not F03's stored 1-day |net| HHI.",
  "evidence": "verification/screener/... (the parity record)" }
```

(Two strings are wrapped here for reading; in the file each is one JSON string. The entry's exact field names follow
`screener-metrics.json` once it exists.) The `max` 20 is derived from the published window (41 sessions), not typed into
code. A companion entry `fl10_effective_buyers` (1/H, unit "brokers") can share the computation.

**L5 worker.** `flowmetrics.ts`: per ticker, per broker, sum n_b over the window on the chosen calendar (P20, D12);
compute H; NA `NULL_AT_EVALUATION` when there is no net buyer; `FLOW_LAGGED` beyond the broker lag limit (P10); the
cell's `eval_date` is the broker as-of date. One ranking pass serves FL07-FL10 (16.10). Cost INFERENCE: about 30-40 ms
for a custom D over the universe.

**Tests.** Parity against the bounded SQL of the proposal (`q13`, one date) on a sample; all-board vs Regular fixture (a
Nego-only broker changes H only on `all`); a stock with no net buyer → NA; D boundaries (1 and 20 pass, 21 refused with
`PARAM_OUT_OF_RANGE`); removing `broker_window` from a fixture index turns FL10 `REQUIRES_DATA`.

**L7 page.** Label "Net-buy concentration (HHI)", unit as a fraction with the effective-buyers figure beside it; the
misuse text in the tooltip; thresholds labelled unvalidated (D10).

**L8 Backtest.** Not transferable (no Backtest condition); `to-backtest.ts` lists it in `left_out` with the reason.

**Deploy.** Migration 2 only if the Phase 2 set also needs F03/F06; worker with the entry (disabled until the file
exists); publisher with `broker_window`; verify. Records: `UPDATE_TABLE.md` gains the rack step after a manual broker
refresh.

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
  `MetricRef`): `{kind: 'series', series: 'USDIDR', field: 'close'}`, valid series read from the catalog.
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

**L5 worker.** Decoder, staleness check, alignment to IHSG's calendar with `asOf` (`datafile.ts:259`, the function the
Backtest uses for IHSG), the series' data version beside `price_data`. Tests: a holiday on one calendar only, a value
published after the cut time, a stale series, the gate failing.

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
- A wire kind for reported values, the first time (PROPOSED, additive): `{kind: 'fundamental', metric: 'roe_ttm'}`. The
  catalog's `fundamentals[]` list already exists in `contract.ts` (`CatalogResponse`) and turns `AVAILABLE` by
  derivation once the file is indexed.
- Entry: unit `percent`, `applies_to` null (all stocks; for a bank-only metric `Industry = Banks`), misuse "ROE is
  inflated by leverage and by small or negative equity; compare within an industry".
- NA reasons: `INSUFFICIENT_HISTORY` (fewer than four quarters), `NOT_APPLICABLE`, and a staleness reason
  (`REPORT_STALE`, PROPOSED) beyond the limit; the cell carries `period` and `published` for the page.

**L5 worker.** Decoder; the value is a universe-level attribute evaluated once per ticker at E (no series); staleness
check; tests with a restated report (the newest vintage available at E wins), a report filed after E (not used), a bank
and a non-bank.

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
| Screener overlay and generated registry | `apps/edge-bff/screener/src/core/screener-overlay.json`, `screener-registry.json` (BRANCH) |
| Screener metric catalog, presets | `apps/edge-bff/screener/src/core/screener-metrics.json`, `presets.json` (PROPOSED) |
| Screener generator | `apps/edge-bff/screener/scripts/build-screener-registry.mjs` (BRANCH) |
| Worker | `apps/screener-worker/` (PROPOSED) |
| edge-bff module and tables | `apps/edge-bff/app/screener.py` (being written); `database/migrations/20261028_001_edge_bff_screener.sql` (BRANCH, not applied) |
| Cross-sectional files at terminal-api | `apps/terminal-api/app/bucket.py` `xsection_index`, `main.py` `xsection` (BRANCH) |
| Page and its words | `apps/edge-bff/screener/`, `src/texts.ts` (BRANCH) |
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
