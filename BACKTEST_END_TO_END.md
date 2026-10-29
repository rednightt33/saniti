# EDGE backtest, end to end

How the EDGE backtest works, from the rows in PostgreSQL to what the browser page draws. Written for the next agent or
person who has to change the backtest or make it faster: read this first, then the code it points to.

- **Verified against:** the code on `main` at `fdd00e7` (2026-10-27, PR #39), plus the documents named in each section.
- **Pointers** are `path` plus a symbol (function, class, constant). Line numbers are avoided because they move; search
  for the symbol.
- **Labels:** FACT is seen in code or a recorded measurement. INFERENCE is derived but not stated or implemented
  directly. OPEN is a known problem without a fix. TEMPORARY is a stopgap that a user decision allowed for now.
- **Where the other details live:**
  - `apps/edge-bff/backtest/CONTRACT.md` is the rule book: every request field, limit, error code and technical
    decision (section 12). This document explains the flow and does not repeat the rules.
  - `ERRORS_AND_SOLUTIONS.md` (entries M244 to M252) has the history and root causes.
  - `RAILWAY_CHANGELOG.md` has every deploy, variable change and measured run.
  - `EXEC.md`, section EXEC-BACKTEST, has the approvals.
- **When this document and the code disagree, the code wins.** Fix this document in the same change.

## 1. The pipeline at a glance

```
 PostgreSQL (Railway "Postgres", sfo)          upstream: idx-price-cron (TradingView), stockbit-updater and
   price, broker flow (Feature 05), events,      stockbit-event-annotation (Stockbit)
   ticker universe, broker list
        │ read-only login terminal_publisher_login
        ▼
 terminal-publisher  ── 07:30 and 19:00 WIB ──▶  bucket terminal-display (sin), prefix v1/
                                                   manifest/{T}.json, price/, broker/, events/, pack/, ref/, state.json
        bucket credentials ▲ (terminal-api only reads manifests and presigns)
 terminal-api (sfo): POST /bundle → presigned GET URLs (120 s) + sha256 and bytes; GET /manifest; GET /reference
        ▲ x-terminal-proxy-key                               ▲ x-terminal-proxy-key, via edge-bff /api/terminal/v1
        │ (private network)                                  │ (session cookie + CSRF)
 backtest-worker (Node 22, sfo, private)         browser: EDGE /backtest → iframe /backtest-app/ (the page)
   downloads the files, checks sha256,             downloads files straight from the bucket host, draws charts and
   runs the engine (shared core)                   the signals preview with the same shared core
        ▲ x-backtest-worker-key                              │
        │ /v1/catalog, /v1/validate, /v1/signals, /v1/jobs   │ /api/v1/backtests/* (session cookie + CSRF)
 edge-bff (FastAPI) ◀────────────────────────────────────────┘
   queue loop, result storage: schema edge_bff (backtest_jobs, backtest_results, backtest_trials)
```

In one paragraph: the publisher copies market tables into sha256-checked gzip JSON files in a
bucket twice a day. terminal-api is the only holder of the bucket key; it hands out two-minute links plus each file's
sha256. The page (served by edge-bff) draws charts and previews in the browser from those files. A run goes from the
page to edge-bff, which validates it with the worker, queues it in its own tables, hands it to the private worker one
job at a time, and stores the finished result (split into parts, 30 days). The worker downloads and verifies the same
files, runs the deterministic event-clock engine of the shared core, and computes the statistics and robustness
checks. The page polls the job and renders the result. No interactive step reads market data from PostgreSQL.

## 2. Parts, where they run, what they hold

| Part | Code | Runs as | Holds | Never |
|---|---|---|---|---|
| Market tables | `database/migrations/`, `DATABASE_SCHEMA.md` | Railway `Postgres` (sfo) | the source rows | — |
| terminal-publisher | `apps/terminal-publisher/publisher.py` | Railway cron, CLI upload, sfo | read-only DB login, bucket write credentials | serves readers |
| Bucket `terminal-display` | written by the publisher | Railway bucket, sin | the published files | — |
| terminal-api | `apps/terminal-api/app/` | FastAPI, 2 processes, CLI upload, sfo | bucket credentials, its own DB login (schema `terminal`: quotas, audit) | streams a data file, lets a client name a key |
| edge-bff | `apps/edge-bff/app/` (`backtest.py` is the whole backtest part) | FastAPI, 1 process, GitHub source (`/apps/edge-bff/**`) | EDGE sessions, `TERMINAL_PROXY_KEY`, `BACKTEST_WORKER_KEY`, its DB login `edge_bff_login` (schema `edge_bff`) | computes a backtest, stores market data |
| backtest-worker | `apps/backtest-worker/` | Node 22, CLI upload, sfo, private network only | `TERMINAL_PROXY_KEY`, `BACKTEST_WORKER_KEY` | holds Postgres or bucket credentials |
| Shared core | `apps/edge-bff/backtest/src/core/` | TypeScript imported by the page and the worker | contract, registry, conditions, engine, statistics, hashes | — |
| Page | `apps/edge-bff/backtest/` (Vite + TypeScript) | static files in edge-bff at `/backtest-app/` | presigned URLs only | holds a storage or database credential |
| Terminal formulas | `apps/edge-bff/terminal/src/calc/indicators.ts`, `terminal/src/data/indRegistry.json` | imported by the core | the 53 indicator formulas | — |

The rules that shape every part (from the user's backtest prompt; CONTRACT.md section 1 and 12):

1. No interactive backtest reads market data from PostgreSQL; everything comes from the published files. Missing data
   is an explicit error (`DATA_MISSING`, `DATA_UNAVAILABLE`, `DATA_INTEGRITY`), never a fallback to PostgreSQL.
2. The worker gets no PostgreSQL and no bucket credentials. Storage credentials never reach the browser.
3. No adjusted close is computed. Postgres-E8GM is not used. market-ai-orc does not execute backtests.
4. Results are deterministic: the same request on the same files with the same `engine_version` and `registry_version`
   gives the same numbers (only `meta.duration_ms` differs).
5. The page is the user's `backtest.html` ported 1:1 (markup and CSS verbatim; a reference copy is in the project
   files at `backtest/reference/backtest.html`). The portfolio stock picker is the one approved change (CONTRACT
   decision PF7). The synthetic data generator exists only in the test fixture build.

## 3. Stage 1: market data in PostgreSQL

The backtest never reads PostgreSQL for market data. The five tables below are read only by the terminal publisher
(section 4). It reads them through the read-only login `terminal_publisher_login`, a member of the group
`terminal_market_reader` only:

- the login is set up by `scripts/provision_terminal_logins.py` with `default_transaction_read_only on`,
  `statement_timeout 120s` and `CONNECTION LIMIT 4`;
- the grants are in `database/migrations/20261025_100_create_terminal_schema.sql` and
  `20261025_101_terminal_reader_event_annotation.sql`.

| Published as | Table (filter) | Columns the publisher reads | Upstream writer | When it changes |
|---|---|---|---|---|
| `price`, `xsection/price` | `Price_Stock_Indonesia_IDX` (`timeframe = 'Daily' AND is_final`) | `ticker, date, open, high, low, close, volume` (NULL for an index); `ingestion_time` only for change detection | `apps/idx-price-cron` (`price_update.py`, TradingView websocket) | Railway cron `0 10 * * *` UTC (17:00 WIB); `idx-price-recovery-cron` at `0 23 * * *` UTC |
| `broker` | `Feature_05_Foreign_Domestic_Broker_Detail` | `ticker, trade_date, broker, investor_type, market_board, buy_value, sell_value, buy_lots, sell_lots, source_balance_gap` | `apps/stockbit-updater` (Stockbit) writes `IDX_Broker_Summary`, then `refresh_feature_05(p_from, p_to, p_tickers)` fills Feature 05 | one round per new Stockbit token, with no cron, so broker data can trail prices by several sessions (ERRORS M243) |
| `events`, `xsection/actions` | `idx_event_annotation` | dates, roles, event family and type, holders, shares and percentages, prices, `value_idr`, `data_origin`; `source_payload` is parsed for corporate-action terms and never published; the term columns `ratio_old`, `ratio_new`, `amount_per_share`, `currency` (filled from the payload through `idx_event_annotation_terms_map`) for `xsection/actions` | `apps/stockbit-event-annotation/job.py`, then `refresh_idx_event_annotation()` | step 4 of each stockbit-updater round |
| `ref/tickers` | `IDX_Stock_Universe` (`"Security Type" IN ('stock','index')`) | `"Ticker", "Company Name", "Security Type", "Sector", "Industry"` (`'Undefined'` = no classification) | migrations and scripts, with no scheduled writer | when the listed universe or a classification changes |
| `ref/brokers` | `IDX_Broker_Profile` | `broker_code, broker_name, broker_type` (broker domicile, a label only) | migrations and scripts | rarely |

Facts that matter downstream:

- **Universe.** 845 tickers: 844 stocks and the index IHSG (`verification/terminal_api/INTEGRITY.md`). There are no
  delisted tickers and no historical index membership. A portfolio is therefore chosen from today's listed stocks
  (CONTRACT.md section 12 records this as survivorship bias).
- **Coverage.** Feature 05 starts on 2016-01-04. Final daily prices start on 2018-01-02 (2,126 sessions up to
  2026-10-26). On 2026-09-17 and 2026-09-18 only IHSG has prices (ERRORS M238, OPEN; the user deferred the fill).
- **Price adjustment.**
  - idx-price-cron asks TradingView for split-adjusted candles for stocks and unadjusted ones for the index
    (`request_symbol`, `"adjustment": "splits"` versus `"none"`).
  - Rows are upserted with `ON CONFLICT (ticker, date) DO UPDATE` and a new `ingestion_time` (`bulk_upsert_prices`).
  - The publisher publishes prices exactly as stored and never adjusts them.
  - The backtest treats the stored history as mixed: back-adjusted for splits, bonus shares and rights before
    2026-09-12, raw after that date. See `ADJUSTED_HISTORY_BOUNDARY` in `apps/edge-bff/backtest/src/core/engine.ts`;
    it is warned about in every result and is decision K4 in CONTRACT.md. How that date was established is not
    recorded (OPEN).
  - No adjusted close is computed anywhere in the backtest. A fix belongs in the data layer (idx-price-cron or the
    price table, decision K4). INFERENCE: corrected closes change the price stamp, so the publisher would republish
    the affected years and packs on its own (section 4).
- **Broker units.** Values are IDR. Lots are 100 shares, with odd lots as fractions. `investor_type` is the source's
  Foreign or Domestic identity, not the broker's domicile (`broker_doc`).
- **Broker source gaps.** For 2016 to 2020 some brokers are missing at the source (FM, LK, maybe TA). Those rows carry
  `source_balance_gap` and are published as a `gap` list; they are not repaired, by user decision (ERRORS M157). The
  broker flow in the files was checked against SQL for 12 tickers and 1,162,017 rows
  (`verification/backtest/FLOW_DATA_CHECK.md`).

## 4. Stage 2: the terminal publisher

`apps/terminal-publisher/publisher.py` (one file) turns the tables into gzip JSON files in the private bucket
`terminal-display`. It is the only writer of the bucket.

### 4.1 Schedule and start

- **Service.** Railway service `terminal-publisher`: region `sfo`, restart policy `NEVER`, Dockerfile
  `CMD ["python", "publisher.py"]`. It is deployed by CLI upload and has no GitHub source.
- **Schedule.** Railway `cronSchedule` `0,30 0,1,12 * * *` (UTC) together with `TERMINAL_RUN_TIMES_WIB=07:30,19:00`.
  The publisher function `cron_for(times)` gives that schedule: the run times and their check times, 30 minutes later
  (`check_times`, EXEC-PUBLISHER-SPEED, ERRORS M303). Before 2026-10-29 it was `0,30 0,12 * * *`.
- **Which ticks run.** `should_run` lets a `daily` run go ahead only within 20 minutes after a listed WIB time, or
  away from every cron tick (a manual run). The other ticks log `skipped`, never connect to the database, and check
  that the last run time's publication came out (`check_publication`: `state.json` `finished_at` at or after that run
  time, else the `missing` alert, section 4.3).
- **Manual runs.** A Railway service with a cron does not run on deploy, and `railway redeploy` keeps the old cron.
  A manual run therefore follows ERRORS M229: clear the cron, set `TERMINAL_PUBLISH_MODE`, `railway up` a new
  deployment, then restore the cron and mode.
- **In the repo.** `.railway/railway.ts` lists the publisher's cron and its variables (`preserve()`), since the
  reconciliation of 2026-10-29 (RAILWAY_CHANGELOG).

### 4.2 One run, in order (`Publisher.run`)

1. `universe()` reads the universe and builds `kind`, mapping each ticker to stock or index. `data_through()` gives the
   global newest date per dataset. `resolve_price_first_year()` derives the first stored year per dataset, today 2018
   for price and 2016 for broker. `state.json` is read for `broker_through`, its `xsection` index (the files of the
   last finished run, `xsection_entries`) and its `refs` index (the content-keyed reference files, `ref_entries`;
   EXEC-MU-RUNTIME T5).
2. **Plan (mode `daily`).**
   - `changed_prices`: one `PRICE_STAMPS_SQL` row per ticker-year gives a stamp
     (`rows=…;last=…;ing=<max ingestion_time>;sum=<sum(close)>`). It is compared with the manifest entry's `stamp`.
     Every listed ticker's manifest is read once before planning, `TERMINAL_BUCKET_THREADS` (16) at a time
     (`load_manifests`, EXEC-PUBLISHER-SPEED): 845 GETs took 8.7 minutes one at a time on 2026-10-29, about 30 s at
     16 (rehearsal).
   - `changed_events`: the same idea per ticker, with `format=2;rows;last;ing`.
   - Broker: the ticker-years of trading dates newer than `state.json` `broker_through`.
3. **Cleanup baseline (mode `daily` only, before the first write).** `cleanup_baseline` lists `state.json` and
   `manifest/` (two requests): the time of the last finished run and of every manifest, kept with the manifests' keys
   and the previous indexes for the cleanup after `state.json` (step 8; section 4.3). Until 2026-10-29 the cleanup
   itself ran here, and a slow listing held the publication 19 minutes (ERRORS M301).
4. **One file (`publish`).** The steps are:
   - SQL for the ticker-year;
   - build the document (`price_doc`, `broker_doc` or `events_doc`);
   - `encode`: compact JSON with `allow_nan=False`, then gzip level 9 with `mtime=0`. Equal rows give equal bytes,
     and `sha256` is the hex digest of the gzip bytes;
   - upload only when the sha256 differs from the manifest entry;
   - update the entry in memory.

   A year that has no rows any more loses its manifest entry; the next daily run's cleanup deletes its object.
   Each data file is written under a **content key**, `{family}/{T}/{name}.{sha256}.json.gz` (`content_key`, `store`):
   a changed file is a new object, and an object is never written again with other bytes (ERRORS M250). An entry whose
   sha256 is unchanged keeps the key it has, including a fixed key from before content keys. Packs (step 5) and the
   xsection files (step 6) are stored through the same `store`.
5. **Packs (`publish_packs`, `put_pack`).**
   - `pack/{T}/price` holds every price year. It is rebuilt when a price year changed or the pack is missing.
   - For stocks, `pack/{T}/broker-archive` holds the broker years up to `last_year - 2`. It is rebuilt when an archived
     year changed, the pack is missing, or its `years` span moved (year rollover). INFERENCE: the first run of a new
     year rebuilds every archive, about 300 MB.
   - Packs cut a stock from 21 objects to 5 for a reader (ERRORS M240: about 0.8 s per object over HTTP/1.1).
6. **Cross-sectional files (`publish_xsection`; EXEC-SCREENER, P1 a, user 2026-10-28).** Whole-universe files for the
   screener-worker, one read per publication instead of one grant per ticker (`XSECTION_REBUILT_BY`: `daily`,
   `backfill` and `packs` rebuild both, `events` rebuilds `actions`, every other mode carries the previous
   `state.json` entries forward unchanged).
   - `price` (`xsection_price`): one statement, `XSECTION_PRICE_SQL` (`PRICE_SQL` without the ticker filter and without
     ORDER BY: one sequential scan, 1,331,548 rows in 5.3 s under EXPLAIN ANALYZE on dev 2026-10-28; with ORDER BY it
     was 7.4 s and an 86 MB sort on disk, so the rows are grouped and ordered in Python). Every published ticker's
     final daily rows from `price_first_year`, ordered by ticker then date, and per ticker `{t, pack_sha256, first,
     last, rows}`. Each ticker's slice is encoded as its price pack (`price_pack_doc`) and compared with the manifest's
     pack sha256; a pack that differs (the table changed after the pack was built, or an older pack the stamps missed)
     is republished from the slice before the manifests are saved, so **every slice equals its published pack**
     (`packs_republished` in the `xsection` log line).
   - `actions` (`read_actions`): one statement, `XSECTION_ACTIONS_SQL` (index scan, 14 ms on dev): family
     `CORPORATE_ACTION`, role `EX_DATE`, types `PRICE_ACTION_TYPES` (the backtest core's list; a test keeps the two
     equal) plus `DIVIDEND`, ex dates from `price_first_year` on, future ones included; tickers outside the universe
     are left out (counted as `outside_universe`); a term of 0 (the source's "unknown") is published as null. Readers
     apply their own rules and windows: the screener's price-break rule takes `ADJUSTED_HISTORY_BOUNDARY` from the
     core.
   - The file is stored through `store` like every data file and pack, under `content_key('xsection', None, name,
     sha)` = `xsection/<name>.<first 16 hex of the sha256>.json.gz` (the form terminal-api's `xsection_index`
     accepts; the index entry carries the whole sha256). `encode` is deterministic, so unchanged rows give the same key,
     and a changed file is a new object: an object is never written again with other bytes (ERRORS M250). A listing of
     `xsection/` (`present_keys`; the cleanup runs after `state.json`, so nothing is deleted during the run) decides
     what is there: a key it holds is not put again, an indexed object it lacks (deleted by hand) is put again
     with the same bytes, and without a listing the previous index stands in for it.
   - A file whose build fails (`xsection_failed`, the error class only) keeps its previous index entry; the rest of the
     run goes on, and the process exits 3 after `state.json`, so the Terminal and the Backtest are never held back by it.
   - Measured locally (PostgreSQL 16, 1.32 M synthetic rows, 845 tickers): `price` about 31 s per run (8 s for the 845
     pack encodes, 18 s for the gzip of its 72 MB of JSON), peak memory 361 MB for the whole daily run; `actions` under
     0.1 s. The dev numbers come with the first dev run (benchmark S15).
7. **Manifests.** `save_manifest` writes the manifest of every touched ticker: `window`, per dataset `data_through` and
   `first_year`, and `generated_at`.
8. **The rest.** `publish_refs` rewrites `ref/tickers.json.gz` and `ref/brokers.json.gz` on every run. Logos are
   refreshed in mode `logos`, or in `daily` when the logo index is more than 7 days old. These fixed keys are written
   exactly as before, for the readers that open them by name. Then `index_refs` (EXEC-MU-RUNTIME T5, user option A
   2026-10-28) stores each reference file of `REF_NAMES` (tickers, brokers, logos: the names terminal-api's
   `REF_FILES` serves, a test keeps the two equal) also under its content key `ref/<name>.<first 16 hex of the
   sha256>.json.gz`: the exact bytes of its fixed-key copy, those written this run or, for logos not refreshed, the
   fixed-key object as it stands. It goes through `store` as the xsection files do, against one listing of `ref/`
   (a key the bucket holds is not put again; without a listing the previous index stands in),
   and these uploads are not counted in `files_written`. A reference file never published (no logo run yet) has no
   entry; one whose copy fails keeps its previous entry (`ref_failed`, the class only) and the process exits 3 after
   `state.json`, as for an xsection file. **`state.json` is written last of the publication**, with `finished_at`, the
   `xsection` index and the `refs` index; nothing is written after it. terminal-api's manifest cache keys on
   `finished_at` (section 6.3). Then, in a `daily` run, the cleanup (`collect_garbage(indexes, before)`, section 4.3)
   deletes what no reader of this or the previous publication can still use; the `done` log line comes before it, with
   the seconds of each step (`phases`) and `threads`.
9. After the evening run, when broker data trails prices (`broker_behind_sessions` ≥ 1), `notify_broker_behind` asks
   telegram-monitor to send an alert (ERRORS M243). Publication alerts (ERRORS M303, section 4.3) go the same way.

Modes (`TERMINAL_PUBLISH_MODE` or `argv[1]`):

| Mode | What it plans |
|---|---|
| `daily` | the scheduled run described above, both xsection files included |
| `backfill` | every ticker-year of every dataset, every pack, both xsection files |
| `broker-range` | broker years `TERMINAL_FROM` to `TERMINAL_TO`, optionally only `TERMINAL_TICKERS`; for a broker correction of past dates, which `daily` does not detect; xsection entries carried forward |
| `events` | changed events files and the `actions` xsection file |
| `logos` | every logo; xsection entries carried forward |
| `packs` | every pack, written only when missing or changed, and both xsection files |
| `verify` | every file listed in a manifest, checked against live SQL (rows, first and last date, a column sum); packs are not checked except through the xsection check; the files of the `state.json` xsection index: bytes and sha256, every `price` slice encodes to its published price pack and has SQL's rows, dates and sum of closes, the `actions` rows equal the statement's; the files of the `state.json` refs index: bytes, sha256 and rows as indexed and byte for byte their fixed-key copy (`verify_refs`); exits 1 on any mismatch |

### 4.3 Guarantees and limits

- **Read-only.** Every statement is a SELECT, and the login is read-only. The two xsection statements are bounded
  (the published years; the corporate-action family, role and types) and were planned with EXPLAIN (ANALYZE, BUFFERS)
  on dev (step 6).
- **No coded ticker list.** The universe comes from the database at run time, and so do the first years.
- **Bytes are deterministic.** A daily run right after a backfill uploads nothing
  (`apps/terminal-publisher/tests/test_publisher.py`).
- **Write order.** Data files, packs and the xsection files; a barrier; the manifests; a barrier; the fixed-key
  reference files and their content-keyed copies; a barrier; `state.json`; then, in a daily run, the cleanup. The
  puts within a step run `TERMINAL_BUCKET_THREADS` (16) at a time (`Uploads`, EXEC-PUBLISHER-SPEED); each barrier
  (`Uploads.wait`) returns only when every put asked so far is in the bucket, and raises the first failure, which ends
  the run before a manifest or `state.json` can name the object. The xsection files and the content-keyed reference
  copies are put at once, so their failure stays theirs (exit 3). A manifest therefore never names a new key that is
  not there yet, and neither do the `state.json` xsection and refs indexes; nothing is written after `state.json`, and
  the cleanup after it deletes only what neither publication names.
- **Not atomic.** A crash leaves the run half done. Restart is `NEVER`, so the next run is up to 12 hours later. The
  objects a crashed run wrote are newer than `state.json`, so the cleanup keeps them until a later run finishes; then
  it deletes those no manifest or index names (an xsection file whose content a later run indexes keeps its key).
- **Bucket requests are asked again (ERRORS M263).** Every bucket call (get, put, each listing page, delete) is asked
  again after 2, 4 and 8 s on a canceled, throttled or 5xx answer or a dropped connection (`transient`, `retried`, log
  `bucket_retry`); any other error, or one that lasts past the third retry, ends the run as before. Since
  EXEC-PUBLISHER-SPEED the client gives up on an answer after 30 s per socket operation (10 s to connect, 3 attempts;
  it was 60 s and 5 attempts, and a hung listing page cost about 6 minutes, ERRORS M301).
- **Alerts (ERRORS M303).** telegram-monitor, source `Terminal_Publisher_Health`, one message per run time and kind:
  `failed` (the step and the error class), `slow` (still going after `TERMINAL_RUN_ALERT_MINUTES`, 30), `partial` (an
  xsection or reference file kept at its previous version, exit 3) and `missing` (a check tick finds no publication
  since the run time; it shares its id with `failed`). The facts come in the request, in fixed shapes only
  (`parse_publisher_health`).
- **Objects never change (ERRORS M250).** Before content keys, a changed file was written again under its fixed key
  while terminal-api still served the previous run's cached manifest, so sha256-checking readers failed
  `DATA_INTEGRITY` during each run. Now a reader holding any manifest or `state.json` xsection index of the last
  finished run downloads exactly the bytes it names, during the whole run: data files, packs (the price pack a slice of
  the xsection `price` file repairs included), xsection files and the content-keyed reference copies all go through
  `content_key` and `store`. Manifests, the fixed-key `ref/<name>.json.gz`, logos and `state.json` keep fixed keys:
  readers open them by name and no reader checks their bytes against a manifest. Since EXEC-MU-RUNTIME T5 a reader of
  the `state.json` `refs` index gets each reference file under a key that names its bytes, with their sha256.
- **Cleanup (`collect_garbage`).** A daily run lists the bucket after its `state.json` (EXEC-PUBLISHER-SPEED; before
  2026-10-29 it listed before its first write) and deletes an object only when all of these hold. With the baseline
  taken before the first write, "the manifest" and "the index" below mean both the previous one and the new one, and
  "`state.json`" means the one the run started from: it deletes exactly what the old cleanup deleted at the start of
  the next daily run, a few minutes later. The conditions: its key is `<family>/<ticker>/<file>` with a family some manifest names (derived from the manifests,
  so a new dataset is covered) and the ticker's manifest names at least one file but not this one, or its key is an
  object of an indexed family (`INDEXED`: `xsection/<name>.<16 hex>.json.gz`, and since EXEC-MU-RUNTIME T5
  `ref/<name>.<16 hex>.json.gz`; nothing else under `xsection/` or `ref/`, so the fixed-key reference files never
  match) and that family's `state.json` index names at least one file but not this one (the index, as
  `xsection_entries` or `ref_entries` reads it, is exactly what terminal-api serves, `bucket.py xsection_index`,
  `refs_index`; a `state.json` without one, from a publisher before that index's writer or a rollback to one, deletes
  no object of that family); that manifest and the object are no newer than `state.json` (the last finished
  run; anything newer may belong to a run that did not finish); and that run finished at least `GC_GRACE_SECONDS`
  (3600) ago, which exceeds the manifest cache check (60 s), the URL lifetime (120 s) and a download. So an object
  goes at the end of the first daily run that finishes an hour or more after the run before it, once no manifest or
  index of either run names it: never sooner than an hour after the run that stopped naming it, and later when another run
  finished in between (each finished run starts the hour again). A reader holding the previous manifest or index keeps
  its files, and two runs minutes apart (a manual run right after a scheduled one) delete nothing. What a `backfill`,
  `packs` or `events` run replaces goes in a later daily run under the same rule. A listing longer than
  `GC_LIST_SECONDS` (900) is abandoned. A failure is logged (`gc_failed`, class only) and the run goes on: cleanup
  never stops a publication. Its log line `gc` gives `deleted`, `not_deleted`, `mb`, `kept_newer_than_last_run`,
  `tickers_skipped`, `families`, `xsection_named`, `refs_named`, `after_publication`; a baseline the bucket could not
  list is `gc_failed` with `step` `baseline`, and the cleanup is skipped.
- **Recorded sizes and times** (`RAILWAY_CHANGELOG.md`):

  | Run | Duration | Written |
  |---|---|---|
  | backfill (2021–2026) | 8,150 s | 284 MB |
  | packs | 4,202 s | 302 MB, 1,656 packs |
  | daily, 2026-10-27 12:00 UTC | 3,496.5 s | 2,492 files, 64.4 MB, 835 tickers |

  INFERENCE: the bucket holds about 0.7 GB.

## 5. Stage 3: storage layout

Bucket `terminal-display` is a Railway S3-compatible bucket in region `sin`. Its host is
`https://<bucket>.t3.storageapi.dev` with virtual-host addressing. Every key is under `v1/`; `Bucket.put` adds the prefix.

| Key under `v1/` | Content | Headers |
|---|---|---|
| `price/{T}/{Y}.{sha256}.json.gz` | `{schema_version: 1, dataset: 'price', ticker, year, units, columns: [d,o,h,l,c,v], d: [...], o: [...], ...}` (columnar; `v` null for an index) | `application/gzip`, `private, max-age=31536000` |
| `broker/{T}/{Y}.{sha256}.json.gz` (stocks) | columns `d, b, i, m, bv, sv, bl, sl` (date, broker, investor type, board, buy and sell value in IDR, buy and sell lots) plus `gap: [[date, board], …]` | same |
| `events/{T}/all.{sha256}.json.gz` | 19 columns, `d, role, family, type, action, …, title, detail`; `format: 2` | same |
| `pack/{T}/price.{sha256}.json.gz` | every price year in one `price_doc` (`dataset: 'price-pack'`) | same |
| `pack/{T}/broker-archive.{sha256}.json.gz` (stocks) | broker years `[broker_first_year, last_year - 2]` (`dataset: 'broker-archive'`, `years: [a, b]`) | same |
| `manifest/{T}.json` | the ticker's index of files (below) | `application/json`, `private, max-age=0` |
| `ref/tickers.json.gz` | columns `ticker, name, type, sector, industry`. Readers take columns by name; every column after `type` becomes a portfolio filter (CONTRACT decision PF6). | gzip |
| `ref/brokers.json.gz` | columns `code, name, type` | gzip |
| `ref/logos.json.gz`, `logo/{T}.png\|svg` | logo index and images (Terminal page) | |
| `ref/<name>.<sha16>.json.gz` (`tickers`, `brokers`, `logos`; EXEC-MU-RUNTIME T5) | the exact bytes of `ref/<name>.json.gz` under a content key (`<sha16>` is the first 16 hex of the sha256), named by `state.json` `refs` | `application/gzip`, `private, max-age=31536000` |
| `xsection/price.<sha16>.json.gz` | `{schema_version: 1, dataset: 'xsection', name: 'price', units, means, columns: [t,d,o,h,l,c,v], t: [...], ..., tickers: [{t, pack_sha256, first, last, rows}]}`: every published ticker's final daily rows from `price_first_year`, ordered by ticker (code point order) then date; a ticker's slice is the rows of its `pack/{T}/price` (`xsection_slices` cuts it by `tickers`); `v` null for an index | `application/gzip`, `private, max-age=31536000` |
| `xsection/actions.<sha16>.json.gz` | `{schema_version: 1, dataset: 'xsection', name: 'actions', units, means, columns: [t, d, type, ratio_old, ratio_new, amount_per_share, currency], ...}`: corporate actions on their ex dates from `price_first_year` (future ones included), ordered by ticker, ex date, type: the share-count changes of `PRICE_ACTION_TYPES` and cash dividends; `amount_per_share` is the dividend per share, for a rights issue its exercise price; a null term is not in the source | same |
| `state.json` | `price_through, broker_through, broker_behind_sessions, window, price_first_year, broker_first_year, last_mode, xsection, refs, finished_at`; `xsection` = `{name: {key, sha256, bytes, rows, as_of}}` with `key` `v1/xsection/<name>.<sha16>.json.gz` (`as_of`: for `price` the newest date in the file, for `actions` the newest `ingestion_time` of `idx_event_annotation`); `refs` = `{name: {key, sha256, bytes, rows}}` with `key` `v1/ref/<name>.<sha16>.json.gz` (`rows`: the rows of the file; no `as_of`, `finished_at` dates the publication; absent from a `state.json` of a publisher before T5) | `private, max-age=0` |

The manifest:

```
{ "schema_version": 1, "ticker": "BBCA",
  "datasets": {
    "price":  { "files": { "2018": {"key": "v1/price/BBCA/2018.<sha256>.json.gz", "sha256": "<64 hex of the gzip bytes>",
                                    "bytes": N, "rows": N, "first": "YYYY-MM-DD", "last": "YYYY-MM-DD", "stamp": "…"}, … },
                "data_through": "<newest final daily date of the whole table>", "first_year": 2018 },
    "broker": { "files": { … }, "data_through": "<newest Feature 05 date of the whole table>", "first_year": 2016 },
    "events": { "files": { "all": { … } }, "data_through": "<newest ingestion_time>", "first_year": … } },
  "packs": { "price": {"key", "sha256", "bytes", "rows", "first", "last"},
             "broker-archive": {"key", "sha256", "bytes", "rows", "first", "last", "years": [2016, 2024]} },
  "window": {"first_year": 2021, "last_year": 2026, "price_first_year": 2018, "broker_first_year": 2016},
  "generated_at": "<UTC ISO>" }
```

- **`data_through` is global.** It is the newest date of the whole table, written into the manifests of the tickers a
  run touched. A ticker's own last date is `files[year].last`. The worker takes the newest broker `data_through`
  across manifests as the flow coverage (CONTRACT section 2).
- **Readers verify, they do not trust.** Every reader of a data file checks its byte count and sha256 against the
  manifest entry. `inflateVerified` in `apps/edge-bff/backtest/src/core/datafile.ts` is shared by the worker and the
  page. Both cache files by sha256 (sections 7.3 and 10). The Terminal page applies the same rule since EXEC-MU-RUNTIME
  T7 (`apps/edge-bff/terminal/src/data/rack.ts readVerified`, on downloaded and cached bytes, and on a reference file
  `/reference` announces with sha256 and size), and asks one new `/bundle` before it shows a failed check; before T7 it
  drew a downloaded file whose sha256 differed and only did not cache it.
- **The fixed-key reference files carry no sha256.** A reader of `ref/<name>.json.gz` downloads it again on each use.
  Since EXEC-MU-RUNTIME T5 each is also under a content key with its sha256 and size in `state.json` `refs`, the same
  bytes, so a reader of that index can check and cache it by sha256 like a data file. The xsection files reuse the
  ticker reference for names, types, sectors and industries; it is not copied into them.
- **Content-keyed reference objects are immutable** for the same reason as the xsection objects below: the bucket holds
  those of the current `refs` index and, until a daily run starts an hour or more after the last finished run, those
  of earlier ones (section 4.3, Cleanup); the fixed-key copies are never deleted.
- **xsection objects are immutable.** `<sha16>` is the first 16 hex of the file's sha256, so a key names one content and
  is written once; readers check bytes and sha256 against the `state.json` index (terminal-api `/state`, `/xsection`).
  The bucket holds the objects of the current index and, until a daily run starts an hour or more after the last
  finished run, those of earlier ones (section 4.3, Cleanup). Their long `max-age` is correct for that reason.
- **Cache-Control is not used.** The `max-age` of a year has no effect today: every presigned URL is new, and readers
  keep their own sha256-keyed caches. With content keys a long max-age is also correct.
- **Keys are never built by a reader.** Every reader takes `key` from the manifest (terminal-api presigns it verbatim),
  so the key format can change without a reader change. A file from before content keys keeps its fixed key
  (`price/{T}/{Y}.json.gz`) until its bytes change.

## 6. Stage 4: terminal-api, the only gate to the files

`apps/terminal-api` is a FastAPI app run as `uvicorn --workers 2`, one replica in `sfo`. It reads manifests from the
bucket, checks quotas, writes an audit row, and answers presigned GET URLs. It never streams a data file itself.
EXEC-MU-RUNTIME Phase 1b (user 2026-10-28, option A; `verification/edge_multiuser/runtime/terminal.md` T1, T3, T5,
T9): service accounts for the workers, the account read inside each grant, the reference file index, `/ready` as the
Railway healthcheck (`.railway/railway.ts`; it answers 200 only once the database holds what the build reads,
`store.py READY`) and `TERMINAL_POOL_MAX` (connections per process, default 8).

### 6.1 Who may call it

- **The backtest's two callers** send a key in the header `x-terminal-proxy-key`:
  - the **worker** calls it directly on the private network, at `TERMINAL_URL`, dev
    `http://terminal-api.railway.internal:8080`, with its `TERMINAL_PROXY_KEY`: the gateway key until the variable
    references its own service key `${{terminal-api.TERMINAL_SERVICE_KEY_BACKTEST_WORKER}}` (EXEC-MU-RUNTIME T1);
  - the **page** goes through edge-bff's proxy (6.4), always with the gateway key.
- **Keys and accounts** (`accounts.py`, `main.py identify`). A request with the header holds the gateway key
  (`TERMINAL_PROXY_KEY`), a service key (`TERMINAL_SERVICE_KEY_<NAME>`, one Railway secret per worker) or is refused
  with 401 `proxy_key_rejected`. There is no fallback to cookies.
  - The gateway key acts as the one subscriber `TERMINAL_PROXY_SUBSCRIBER` (dev `edge-owner@terminal.local`, subscriber
    2), kind `person`. Every page request, and every worker request while the worker presents the gateway key, is
    booked on that account. This is TEMPORARY, decision U1 in CONTRACT.md; its quotas are overridden to 1,000,000,000
    (TEMPORARY, `verification/terminal_api/jobs/quota_unlimited_edge_owner.sql`).
  - A service key acts as its own account `<name>@terminal.local` (`terminal.subscriber.kind = 'service'`, migration
    `20261028_100`: `backtest-worker`, `screener-worker`): its own advisory lock and audit rows; counted per clock hour
    (UTC) in `terminal.usage_hour` against the ceilings `service_grants_per_hour`, `service_files_per_hour` and
    `service_megabytes_per_hour` (a runaway guard, not a person's quota; 429 `service_ceiling_reached`); never signs
    in; can never name an owner (400 `owner_not_allowed` with `x-terminal-proxy-owner`); published files only (403
    `not_for_service_accounts` on `/history` and the password route); 401 `service_account_inactive` when its row is
    missing, inactive or expired.
  - The account is checked (active, unexpired) inside each grant's transaction, after its lock (T3, `main.py admit`):
    a grant never passes for an account deactivated while it waited. `/manifest`, `/state` and `/logo` grant nothing
    and use this process's last check of the same key, at most 60 s old (`AccountCache`): a deactivated account can
    read those for up to 60 s more.
- **Direct subscriber sign-in is not on the backtest path.** terminal-api also serves its own sign-in (cookie
  `terminal_session`), yearly `/files`, a PostgreSQL `/history` for dates before the published years, `/logo` and
  admin routes.
- **The screener-worker** (EXEC-SCREENER, user 2026-10-28) calls terminal-api on the private network: `/state`,
  `/manifest`, `/reference` and `POST /xsection`. `/xsection` admits the screener-worker's service key and, until a
  later step removes it from the workers, the gateway key (6.2).

### 6.2 The routes the backtest and the screener use

| Route | Used by | What it does |
|---|---|---|
| `POST /api/terminal/v1/bundle {ticker, datasets, packs: true}` | worker and page | see the steps below |
| `GET /api/terminal/v1/manifest/{T}` | worker only (freshness and coverage checks) | `{ticker, window, generated_at, datasets: {name: {data_through, years: {id: {bytes, rows, first, last, sha256}}}}}`. No object key, no URL, no quota, no audit row. |
| `GET /api/terminal/v1/reference/{tickers\|brokers}` | worker only (catalog, validation) | one presigned URL: of the content key `v1/ref/<name>.<16 hex>.json.gz` when the publication's `refs` index (`/state`) names the file, the answer then adding its `sha256`, `bytes` and `rows` and its bytes counting; otherwise (a publication before EXEC-MU-RUNTIME T5, or a name the index lacks) of the fixed key `REF_FILES`, with those three fields null. The bytes are the same either way. Counted against quota (pseudo-ticker `REF`, never an opened ticker); a name neither in the index nor in `REF_FILES` is 404 `unknown_reference` |
| `GET /api/terminal/v1/state` | the backtest worker (EXEC-BACKTEST-LOAD, 2026-10-27) and the screener-worker (EXEC-SCREENER). The code admits any account (`Depends(reader)`: the gateway key, a service key or a session cookie, from this process's check at most 60 s old), since it grants nothing; edge-bff does not forward it | the publication the files belong to: state.json `finished_at`, `price_through`, `broker_through`, `broker_behind_sessions`, as read for the manifest cache (at most 60 s old), and `xsection`, the run's cross-sectional file index `{name: {key, sha256, bytes, rows, as_of}}` (`bucket.py xsection_index`: only well-formed entries, a key `v1/xsection/<name>.<16 hex>.json.gz` whose 16 hex are the first 16 of its `sha256`, each with these five fields; null when the run wrote none; the publisher carries forward and protects from its cleanup exactly these entries, `publisher.py xsection_entries`); and `refs` (EXEC-MU-RUNTIME T5), the run's reference file index `{name: {key, sha256, bytes, rows}}` (`bucket.py refs_index`, the same rules under `v1/ref/`; null when the run wrote none), which `/reference` grants from. No file, no quota, no audit row. 503 `state_unavailable` while state.json was never readable. |
| `POST /api/terminal/v1/xsection {names}` | the screener-worker only, not the backtest: its service key (`TERMINAL_SERVICE_KEY_SCREENER_WORKER`) or, until a later step removes it, the gateway key; any other caller, another service or a subscriber session included, is 403 `gateway_only` (`main.py xsection_caller`); edge-bff does not forward it | presigned URLs for files of the `/state` index, named by their index names: `{finished_at, expires_in_seconds, encoding, files: [{name, url, sha256, bytes, rows, as_of}]}`. 1 to 16 names (a repeated name counts once); a name not in the index is 404 `xsection_not_published` with the indexed names. One file per name and their bytes count against the quota under the pseudo-ticker `REF` (never an opened ticker; for the service account its hourly ceilings), with one `terminal.access_log` row (dataset `xsection`) listing every key; 429 `quota_exceeded` (`service_ceiling_reached`) refuses every name. |

What `/bundle` does:

1. Read the manifest (6.3).
2. Choose the files. Price is the price pack when one exists. Broker is the broker archive, then the yearly files after
   its last year. Events is the `all` file. A dataset the ticker does not have answers no files and no error.
3. `grant`: in one transaction under `pg_advisory_xact_lock(hashtext('terminal.subscriber'), sid)`, read the account
   again (401 when it is no longer active), check the quota (429 `quota_exceeded` for the whole bundle) or, for a
   service account, add the grant to its clock hour in `terminal.usage_hour` and check its ceilings (429
   `service_ceiling_reached`; a refused grant is rolled back), and write one `terminal.access_log` row that lists every
   key.
4. Presign each manifest `key` for `url_ttl_seconds`: 120 s by default, from table `terminal.quota`.
5. Answer `{ticker, window, generated_at, expires_in_seconds, datasets: {name: {data_through, first_year, files: [{year,
   url, sha256, bytes, rows, pack?}]}}}`.

A client never names an object key. Only manifest keys, the fixed `REF_FILES` keys and the keys of the `state.json`
xsection and refs indexes are presigned.

### 6.3 The manifest cache (`apps/terminal-api/app/bucket.py`, `Bucket._fresh`, `Bucket.manifest`)

- **What is cached.** Each process keeps every manifest it has read, including "not found", in memory. That avoids
  about 1 s per read across regions (`sfo` to `sin`).
- **When it is cleared.** At most every `manifest_cache_seconds` (60, a constant in `config.py` with no environment
  variable), `_fresh` reads `v1/state.json`. The whole cache is cleared when `finished_at` changed or there are more
  than `MAX_CACHED` (4000) entries. An unreadable `state.json` keeps the cache.
- **Consequences:**
  - After a publisher run, every process serves new manifests within about 60 s.
  - During a run, terminal-api keeps serving the manifests of the previous run. Content keys keep the bytes those
    manifests name readable (M250); the publisher's cleanup waits an hour after the last finished run.
  - A ticker first published after its "not found" was cached stays 404 until the next `finished_at`.
- **The publication.** `/state` and the xsection and refs indexes `/xsection` and `/reference` grant from come from the
  same read of `state.json` (`Bucket.state`), so all are at most 60 s old. For up to 60 s after a run one of the two
  processes can answer the new publication and the other the previous one. `/xsection` answers its `finished_at` and
  each file's sha256, so a caller compares them with the `/state` index it acts on; the xsection keys are
  content-addressed and never overwritten, so a file granted from the previous index is still that index's file.

### 6.4 The page's route: browser, edge-bff proxy, terminal-api (`apps/edge-bff/app/main.py`)

1. **Proxy route.** The page calls `/api/terminal/v1/{path}` on edge-bff with the EDGE session cookie. A POST also
   carries `Origin` (the `protections` middleware: it must equal `EDGE_PUBLIC_ORIGIN`, and the body is capped at
   131,072 bytes) and `X-CSRF-Token` (HMAC-SHA256 of the session token, dependency `write`).
2. **Forwarding.** `forward_terminal` forwards only paths that fully match `TERMINAL_ROUTES`: GET `manifest/T`,
   `reference/...`, `history/...` and `logo/T`; POST `files` and `bundle`. Anything else is 404 before any call. The
   request goes to `EDGE_TERMINAL_URL`, which must be `http://terminal-api.railway.internal` when deployed. It carries
   only `content-type` and `x-terminal-proxy-key`; browser cookies are never forwarded. One pooled
   `httpx.AsyncClient(timeout=30)` per process is used.
3. **Answers.** terminal-api's JSON comes back with its status, so `{error, message}` reaches the page unchanged. A
   connection error, a timeout or a non-JSON body is 503 `TERMINAL_UNAVAILABLE`.
4. **Download.** The browser downloads the presigned URL directly from the bucket host. This is allowed by the frame's
   CSP, `BACKTEST_CSP = TERMINAL_CSP` with `connect-src 'self' https://*.t3.storageapi.dev`, and by the bucket's CORS
   rule: GET and HEAD from the EDGE origins (`scripts/terminal_bucket_cors.py`). EDGE's own shell has
   `connect-src 'self'` and cannot reach the bucket. Storage credentials never reach the browser; it only ever holds
   presigned URLs.

### 6.5 Numbers, failures, costs

- **Measured from the worker** (`apps/backtest-worker/README.md`).

  | Worker region | `/bundle` (median) | File download (median) | Catalog build |
  |---|---|---|---|
  | `sfo` (next to terminal-api) | 166 ms | 2,268 ms | 2.3 s |
  | `sin` (next to the bucket) | 892 ms | 448 ms | 22.3 s |

  The worker runs in `sfo`.
- **Concurrent `/bundle` calls with packs:** median 0.23 s for 1 call and 0.53 s for 20 (ERRORS EXEC-TERMINAL-SPEED).
- **Failures as the readers see them:**

  | Situation | Worker (`apps/backtest-worker/src/terminal.ts`) | Page (`apps/edge-bff/backtest/src/api/live.ts`) |
  |---|---|---|
  | `/bundle` lists no file for the dataset | `DATA_MISSING`; a portfolio leaves the stock out | `DATA_MISSING` |
  | 404 `unknown_ticker` | `DATA_MISSING`; a portfolio leaves the stock out | terminal-api's message, code `unknown_ticker` |
  | 429 `quota_exceeded` (worker with its service key: `service_ceiling_reached`) | `DATA_UNAVAILABLE` | "Limit reached: …" |
  | 401 (key or gateway account) | `DATA_UNAVAILABLE` | "Sign in to EDGE first", which is misleading for a gateway-key problem |
  | Bucket 403 (URL expired) | asks a new `/bundle` once | `DATA_UNAVAILABLE` (403); the next chart load asks a new `/bundle` |
  | Bucket 404 | `DATA_MISSING` | `DATA_UNAVAILABLE` (404) |
  | No answer, cut-off body or 5xx | retried `BACKTEST_DOWNLOAD_RETRIES` times with backoff | retried twice (`FILE_RETRIES`, 500 ms then 1000 ms; ERRORS M251) |
  | Size or sha256 mismatch | `DATA_INTEGRITY`, never retried | `DATA_INTEGRITY`, never retried |

- **Cost of each page call through the proxy** (FACT):
  - one new PostgreSQL connection in edge-bff for the session check (`Store.connect` per call);
  - one pooled HTTP request;
  - in terminal-api (T3), for `/bundle` and `/reference` one transaction: the advisory lock, the account read, the
    limits, the usage aggregate and an INSERT; for `/manifest`, `/state` and `/logo` none. One account read in its own
    transaction comes first only when this process has not checked the key in the last 60 s. Measured on a disposable
    PostgreSQL 16 with the gateway key (`apps/terminal-api/scripts/measure_grant_transactions.py`): 2.0 transactions
    per grant and 1.0 per read before, 1.0 and 0 after.
- **Shared lock.** Every grant of the page, and of a worker while it presents the gateway key, serializes on one
  subscriber lock; a worker with its service key takes its own account's lock.
- **OPEN (security, dev):** terminal-api's public domain accepts the gateway key from anywhere; the code does not
  check where a proxied request comes from (`proxied`).

## 7. Stage 5: the worker (`apps/backtest-worker`)

A private `node:http` service; edge-bff (`WorkerClient` in `apps/edge-bff/app/backtest.py`) is its only caller and the
page never reaches it. No npm dependency: `node --experimental-strip-types --import ./loader/register.mjs
src/server.ts`. The loader resolves the Terminal's Vite-style extensionless imports (ERRORS M249). The Docker image
(`Dockerfile`, build context = repo root) copies the worker, the shared core, `terminal/src/calc` and
`terminal/src/data/indRegistry.json`.

### 7.1 Start and every request

- `loadConfig` (`src/config.ts`) and `checkRegistry` (`src/version.ts`) run first; a bad variable or a stale
  `backtest-registry.json` exits 1. `ENGINE_VERSION` is a 16-hex hash of every core file and `src/*.ts`;
  `REGISTRY_VERSION` a hash of `indRegistry.json` and `indicators.ts` (`scripts/build-registry.mjs registryVersion`).
- Two long-lived `worker_threads` (`src/compute.ts ComputeThread`): `jobs` and `previews`, so status, cancel and health
  stay answered while a job computes. One job and one preview compute at a time.
- Every route but `/health` needs `x-backtest-worker-key` (`crypto.timingSafeEqual`), else 401.

### 7.2 Routes (`src/server.ts`; full rules in CONTRACT.md section 8)

| Route | What happens |
|---|---|
| `GET /v1/catalog` | `buildCatalog` (`src/catalog.ts`): both reference files, an IHSG `/bundle` (calendar `data_through`, `first_date`), with flow on the publication's `broker_through` (terminal-api `/state`; without it, the newest broker `data_through` over every stock's `/manifest`, `load.ts brokerDataThrough`), groupings from the ticker columns, the limits. Kept per publication (`ByPublication`: `/state` asked at most every 60 s, a new `finished_at` builds again); built at start (`warm`). The reference lists for validation, previews and jobs are kept the same way. |
| `POST /v1/validate {request}` | `checkRequest` (`src/validate.ts`: allow-listed fields, then the core's checks), `canonicalRequest`, then `checkPublished` (`src/run.ts`): manifests only, never `/bundle`: `FLOW_DATA_THROUGH`, IHSG `last_bar` (`PERIOD_AFTER_DATA`). Answers `{ok, lineage_key, variant_hash, tickers}` |
| `POST /v1/signals` | the preview: FIFO queue, one at a time on the `previews` thread; the deadline covers the queue wait; a caller that leaves is removed or its thread task cancelled (`runSignals`) |
| `POST /v1/jobs {job_id, request, context}` | `checkJobBody` (`job_id` `bt_` + 32 hex; `context.prior_trials`), the same id again = 202 (idempotent), another job running = 409 `BUSY`, `checkRequest` again (a refusal never becomes a job), then `startJob` on the `jobs` thread with a timeout |
| `GET /v1/jobs/{id}`, `/result`, `POST /cancel` | status; the stored gzip result (repeatable; 410 `RESULT_GONE` once a newer job replaced it); cancel sets an `Atomics` flag the thread reads between phases, tickers and every 256 engine steps |

Only the latest job is kept, in memory; after a restart every id is 404 `UNKNOWN_JOB`, which edge-bff turns into
`WORKER_LOST`.

### 7.3 One job, in order (`src/run.ts runJob`)

1. `checkRequest` again, `canonicalRequest` (picked stocks sorted, PF3).
2. `loadMarket` (`src/load.ts`): group 1 = IHSG price; group 2 = the tickers' price + events (+ broker when the
   request reads flow; portfolio groups skip unpublished stocks as `excluded`).
   - Step 1: one `/bundle` per ticker, `BACKTEST_DOWNLOAD_CONCURRENCY` lanes. Then `planned` (`FLOW_DATA_THROUGH`)
     and the limits on the manifest sizes (`BACKTEST_MAX_DOWNLOAD_BYTES`, `BACKTEST_MAX_BROKER_ROWS`), before any
     download, whether or not files are cached, so the answer never depends on the cache.
   - Step 2: per ticker, a new `/bundle` only when the first answer is no longer `usable` (age +
     `BACKTEST_HTTP_TIMEOUT_MS` ≥ the URL lifetime) and a file is not cached; one more after a bucket 403.
   - `TerminalClient.file` (`src/terminal.ts`): memory LRU, then the shared disk cache `BACKTEST_CACHE_DIR` (files
     `<sha256>.json.gz`, written to a temp name then renamed), else a GET capped at the manifest `bytes`; every copy,
     cached or not, goes through `inflateVerified` (sha256 + size) on every use. In-flight downloads of one file are
     shared.
   - `data_version = dataVersion(files)` (core `datafile.ts`): a hash of the files read.
3. `checkAfterData`, `checkPriceRange` (single), `MarketData`, then the engine: `prepare` + `run` (section 9), progress
   `signals` then `backtest`.
4. Sensitivity grid (`sensitivityPlan`): up to 25 cells, de-duplicated by variant hash, the run reused as its own cell.
5. `lineageKey`, `requestHash`, Monte Carlo (`monte_carlo` phase), `buildResult`, `finalizing`; `packResult` caps the
   JSON at `BACKTEST_MAX_RESULT_BYTES` and gzips it; the gzip buffer is transferred to the main thread.

### 7.4 Numbers (dev, `apps/backtest-worker/README.md`, 2026-10-27)

- Single stock with flow: 1.31 s cold (6 files, 1.25 MB), 0.45–0.58 s warm, result 357 KB JSON (95 KB gzip).
- 12-stock portfolio: 7.05 s cold (60 files, 28.35 MB in 6.1 s), 5.5 s warm, 944 KB JSON (274 KB gzip).
- Disk cache: a preview downloaded 48 files (28 MB); the job after it downloaded 12 (0.08 MB) and took 4.7 s.
- Memory peak 1.31 GB (preview + run + cancel), CPU 0.43 vCPU. Largest file: BBRI broker archive, 2.2 MB gzip,
  14.5 MB inflated. Heaviest valid result about 3.8 MB JSON (4,176 trades).
- Dev variables (names; values in README): `BACKTEST_TIMEOUT_SECONDS` 900, `BACKTEST_MAX_RESULT_BYTES` 33,554,432,
  `BACKTEST_MAX_DOWNLOAD_BYTES` 1.5 GB, `BACKTEST_MAX_BROKER_ROWS` 20,000,000, `BACKTEST_CACHE_BYTES` 1.5 GB,
  `BACKTEST_CACHE_DIR` `/tmp/backtest-cache` (1 GiB), `BACKTEST_DOWNLOAD_CONCURRENCY` 16, retries 3 (base 500 ms),
  `BACKTEST_HTTP_TIMEOUT_MS` 60,000, `BACKTEST_MAX_CONDITIONS` 32, `BACKTEST_FLOW_ENABLED` 1, positions and portfolio
  stocks at most 12 (core `MAX_POSITIONS`, `MAX_PORTFOLIO_TICKERS`, only lowerable).

## 8. Stage 6: edge-bff, the public API and the queue (`apps/edge-bff/app/backtest.py`)

edge-bff never computes and never stores market data. It reads only a few fields of a request (mode, ticker, picked
stocks) and of a result (versions, duration, trials, lineage key, events). Off (503 `BACKTEST_DISABLED`) when
`BACKTEST_WORKER_URL` is empty; 503 `BACKTEST_NOT_READY` until the tables exist.

### 8.1 Routes (class `Backtests`; session cookie on every route, `Origin` + `X-CSRF-Token` on every POST)

| Route | What happens |
|---|---|
| `GET /api/v1/backtests/catalog` | worker `/v1/catalog`, cached 60 s in process (`CATALOG_CACHE_SECONDS`); on a worker failure the last catalog is kept |
| `POST /api/v1/backtests` (202) | `client_request_id` (absent = never idempotent); an existing one with the same request answers the same job (`same_request`), another request is 409 `SUBMISSION_CONFLICT`; else worker `/v1/validate` (its 422 and 424 relayed), then `BacktestStore.submit` under an owner lock: 429 `QUEUE_FULL` beyond `BACKTEST_QUEUED_PER_OWNER` (3), INSERT `bt_` + 32 hex |
| `GET /api/v1/backtests`, `GET …/{id}` | list (30, max 100) and status (`status_of`: state, progress, error, times, sizes) |
| `GET …/{id}/result` | the `core` part (sha256 re-checked: 500 `RESULT_INTEGRITY`; 410 `RESULT_EXPIRED` after retention); single mode merges the ticker's events part into it; sent gzip when the browser accepts it |
| `GET …/{id}/events?ticker=` | one ticker's events part (portfolio charts) |
| `POST …/{id}/cancel` | QUEUED → CANCELLED at once; RUNNING → `cancel_requested`, which the loop sends to the worker |
| `POST /api/v1/backtests/signals` | the preview, latest wins per owner and page (`client_order {page, seq}`; an older seq is 409 `PREVIEW_REPLACED` before reaching the worker; an older call in flight is cancelled; a caller that left gets 204; ERRORS M247) |

### 8.2 The queue loop (`BacktestLoop`, started in `lifespan` when `EDGE_WORKER_ENABLED`)

1. Every poll (`EDGE_POLL_SECONDS`, 2): hourly prune of results older than 30 days; `reap` RUNNING jobs whose lease
   expired → FAILED `WORKER_LOST` (never re-queued); `claim` the oldest QUEUED job of an owner without a RUNNING one
   (`FOR UPDATE SKIP LOCKED`), set a new `lease_token` and `lease_expires_at` (`EDGE_LEASE_SECONDS` 90, heartbeat 20).
2. `dispatch`: the line's `prior_trials` (in `recorded_seq` order), then worker `POST /v1/jobs {job_id, request,
   context}`. `BUSY` waits; 3 unanswered calls → `WORKER_LOST`.
3. `follow`: poll `GET /v1/jobs/{id}`, store `progress` when it changed; FAILED/CANCELLED end the job with the
   worker's error; past `BACKTEST_TIMEOUT_SECONDS` → `TIMEOUT` (or `RESULT_NOT_STORED` when a fetched result could not
   be stored).
4. `ingest`: stream the gzip result (inflated up to `BACKTEST_MAX_RESULT_BYTES`, else `LIMIT_EXCEEDED`), `split_result`
   into `core` + one `events:<ticker>` part per ticker (each gzip JSON with a sha256), then `BacktestStore.finish` in
   one transaction: FINISHED with versions and `data_version`, the parts, and the trials UPSERT
   (`backtest_trials`, unique per owner, lineage and variant; `recorded_seq` kept).
5. Every write after the claim is fenced by the lease token (ERRORS M246); a database failure a retry may mend is
   retried until the job's deadline.
6. Measurement (EXEC-MU-RUNTIME Phase 0; `verification/edge_multiuser/runtime/backtest.md` section 7): log lines only,
   nothing decides on them. edge-bff: `backtest_submit` (with `request_key`, the hash of the request in the worker's
   canonical form, for the share of identical requests), `backtest_claim`, `backtest_poll` per status read,
   `backtest_job_timing` per job (queue wait, hand-over, the worker's time, the poll slack, download, split, store, end to
   end) and `backtest_preview` (`apps/edge-bff/README.md`). The worker: `job_end` with `phases_ms` per status phase and
   the memory, `preview_end` with each preview's queue wait (`preview_wait_ms`) and compute time (worker README, Logs).
   A worker source change changes `engine_version` (section 7.1); it is recorded for the Screener build's tripwire in
   `scripts/screener/backtest_worker_baseline.json`.

Tables (`database/migrations/20261026_005_edge_bff_backtest.sql`): `edge_bff.backtest_jobs` (one RUNNING per owner,
unique partial index), `edge_bff.backtest_results` (`(request_id, part)`, bytea, sha256, 30 days), and
`edge_bff.backtest_trials` (never reset; trials outlive jobs). The runtime role gets exactly the grants the
migration's `$verify$` block checks.

### 8.3 Serving the page

- `GET /backtest` serves EDGE's SPA (`static/index.html`); its `BacktestPage` renders `<iframe src="/backtest-app/">`.
- `GET /backtest-app/` and `/backtest-app/assets/{name}` (immutable, one year) serve the Vite build with
  `BACKTEST_CSP` (`script-src 'self'`, `connect-src 'self' https://*.t3.storageapi.dev`).
- `apps/edge-bff/Dockerfile` stage `backtest` (`node:22-slim`): `npm ci`, copies `terminal/src` beside the page
  (the core imports it), `npm run build` (`tsc --noEmit && vite build`), and the final Python image copies `dist` to
  `static/backtest-app`. So the page is deployed with edge-bff: a push to `main` touching `/apps/edge-bff/**` rebuilds
  both (but see ERRORS M252, section 12).

## 9. Stage 7: the engine (shared core, `apps/edge-bff/backtest/src/core`)

Pure TypeScript, no I/O; the same modules run in the browser (charts, preview) and in the worker (runs).

| File | Role |
|---|---|
| `contract.ts` | the request, result, catalog, job status and preview types |
| `registry.ts`, `backtest-registry.json` | the 53 indicators of the Terminal (outputs, parameters, ranges), generated by `apps/backtest-worker/scripts/build-registry.mjs` from `terminal/src/data/indRegistry.json` and `calc/indicators.ts` `DEFAULTS`; formulas are imported from `indicators.ts`, never copied |
| `conditions.ts` | condition kinds (indicator, price action, flow), operators, "within N bars", `combineEntry`, `combineExit` |
| `signals.ts` | entry events per period (`periodSignals`), ranking, `EXCLUDED_CODES`, the preview row |
| `flow.ts` | broker flow series (foreign net and friends) from broker rows |
| `datafile.ts` | decoding the published files, `inflateVerified` (size + sha256), `priceSeries`, `brokerRows`, the as-of close, `dataVersion` |
| `engine.ts` | the calendar and the event clock: `prepare`, `run`; `MAX_POSITIONS`, `MAX_PORTFOLIO_TICKERS`, `ADJUSTED_HISTORY_BOUNDARY` |
| `ledger.ts`, `result.ts` | trades and equity into the result |
| `stats.ts`, `robustness.ts` | series and trade statistics; Monte Carlo, sensitivity, deflated Sharpe, `trialSet` |
| `hash.ts` | `canonicalRequest`, `variantOf`, lineage key, variant hash, `requestHash` |
| `catalog.ts` | page catalog, templates, `DISPLAY` units |

How a run works (rules in CONTRACT.md sections 4 to 7):

- **Calendar**: the union of the published bar dates of IHSG and the picked stocks inside the period (on today's data
  it equals IHSG's). A day without a bar for a ticker: it cannot trade and is marked at its last close.
- **Signals**: an entry event is a bar where the combined entry state turns from false to true on the ticker's own
  bars; it orders a buy at the next calendar day's open (skipped `no_next_bar` when the ticker has no bar).
- **Event clock per day**: before the open, trailing levels; **open**: stops, targets and pending exit signals sell at
  the open, then entries (portfolio: liquidity filter, ranking by `adx`, `fnet`, `vol` or `rsi`, free slots, ARA open
  gap skip), sized in lots of 100 with fees and slippage, no leverage; **intraday**: stop before target when both are
  touched; **close**: time exit, exit signal for the next open, `end_of_test` on the last day; **mark**: equity at the
  close.
- **Results**: the page's own formulas (`seriesStats`, `tradeStats`, `dsr`, `monteCarlo`), in-sample/out-of-sample
  split, benchmark (buy and hold or IHSG), sensitivity grid, warnings (`PERIOD_CLIPPED`, `TICKERS_EXCLUDED`,
  `SURVIVORSHIP`, `ADJUSTED_HISTORY_BOUNDARY`, `DATA_GAP`, `ARB_NOT_MODELLED`, `TICK_NOT_MODELLED`), and events per
  ticker for the charts.
- **Trials**: the lineage key is the strategy's shape (no numbers); the variant hash is what the engine reads in a
  canonical form. edge-bff passes the line's prior trials, the run adds its own, and the deflated Sharpe uses them.
- **Determinism**: no clock or random number reaches a number (Monte Carlo is seeded by the request); `engine_version`,
  `registry_version` and `data_version` are stored with every job, so a different number is always explainable.

## 10. Stage 8: the page (`apps/edge-bff/backtest`, outside `src/core`)

1. **Boot** (`src/main.ts`, `src/app.ts`, `src/env.ts`; EXEC-BACKTEST-LOAD 2026-10-27): `GET /api/v1/backtests/catalog`
   and the shown ticker's prices are asked at once and the builder and chart are drawn without waiting for them (what
   answers within 60 ms is used for the first render); until the catalog answers the page runs on `env.ts
   PROVISIONAL` and the lists it fills say they are loading; Run waits for it (CONTRACT section 10, Loading). The
   session's CSRF token (`GET /api/v1/auth/session`) is read with the first POST. No run at load (the page opens "Not
   run yet").
2. **Build the strategy** (`src/state.ts`, `builder.ts`, `workspace.ts`, `reg.ts withinLimit`): the reference's
   builder; the condition limit is the catalog's `max_conditions`. Portfolio mode: the stock picker (`picker.ts`,
   rules in `picked.ts`): search, sector and industry filters from `catalog.groupings`, at most
   `limits.max_portfolio_tickers` (12).
3. **Charts and preview data** (`src/api/live.ts`, `api/load.ts`, `api/load.worker.ts`, `api/compute.ts`): one
   `/bundle` per ticker for its prices and, when a flow card will need them, its broker files (reused while the URLs
   are good); in a Web Worker the files are read from the browser cache or downloaded from the bucket (two retries),
   checked (`inflateVerified`) and decoded into the price series or the broker flow; the cache and the download are
   `terminal/src/data/rack.ts`, the module the Terminal uses (IndexedDB `terminal-files`, 50 MB, least recently used).
   The candles draw once the prices are there; flow lanes and the entry lane say they are loading until the broker
   data is there. Indicator lines and condition series are computed in the browser with the shared core.
4. **Signals preview** (`src/preview.ts`, `signals.ts`): `POST /api/v1/backtests/signals` with `client_order`; only the
   latest answer is drawn; `PREVIEW_REPLACED` is not an error.
5. **Run** (`src/run.ts`, `api/request.ts buildRequest`): submit with a `client_request_id`; poll the status every
   second (`POLL_MS`; a cut-off answer is asked again); then `/result`, and `/events?ticker=` for the run's tickers;
   Cancel calls `/cancel`. Errors come back as `{error: {code, field, message}}` and are shown as toasts
   (CONTRACT section 11).
6. **Render** (`src/results/*`: overview, returns, trades, risk, robust, list, `svg.ts`), formats and toasts
   (`format.ts`), layout (`layout.ts`), styles (`styles/backtest.css`, the reference's CSS verbatim plus the picker's
   `.pk-*` layout rules).

The test build `?fixture=reference` (the synthetic market and the reference's mock-up engine, `tests/fixture`) exists
only for the visual and numeric comparison with `backtest.html`, and is checked absent from the production bundle.

## 11. Cross-cutting

### 11.1 Caches, from the bucket to the screen

| Where | What | Key | Lifetime |
|---|---|---|---|
| Bucket (publisher) | data files, packs, xsection files | key with the content's sha256 (`content_key`; xsection: its first 16 hex) | never rewritten; deleted at the end of the first daily run that finishes an hour or more after the run before it, once no manifest or index of either run names it (`collect_garbage`, section 4.3) |
| terminal-api process | manifests, "not found" too | ticker | until `state.json` `finished_at` changes (checked every 60 s) |
| terminal-api process | `state.json`: the `/state` answer and the xsection index `/xsection` grants from | — | read again at most every 60 s; an unreadable `state.json` keeps the last one |
| Presigned URL | access to one key | — | 120 s |
| Worker memory (per thread) | verified gzip bytes | sha256 | LRU, `BACKTEST_CACHE_BYTES` |
| Worker disk (shared by threads) | verified gzip bytes | `<sha256>.json.gz` | LRU, `BACKTEST_CACHE_DIR_BYTES`, lost on redeploy |
| Browser IndexedDB `terminal-files` | verified gzip bytes | sha256 | LRU, 50 MB, shared with the Terminal |
| Worker process | catalog, reference lists | `/state` `finished_at` | until the next publication (checked at most every 60 s) |
| edge-bff process | catalog | — | 60 s |
| edge-bff `backtest_results` | result parts | `(request_id, part)` | 30 days |

Every byte cache is keyed by content (sha256), so a republished file never serves stale bytes, and the bucket key of
every data file, pack and xsection file carries its content too (ERRORS M250); caches hold gzip bytes, so a warm run
still pays sha256, inflate and decode.

### 11.2 Errors, from where they start

| Code | Raised by | Meaning |
|---|---|---|
| `INVALID_INPUT`, `UNKNOWN_FIELD`, other 422 validation codes | worker `validate.ts` (core checks), edge-bff body checks | the request is wrong; never becomes a job |
| `FLOW_DATA_THROUGH`, `PERIOD_AFTER_DATA`, `PERIOD_EMPTY`, `PERIOD_BEFORE_DATA`, `UNIVERSE_EMPTY` | worker (manifests or the loaded data) | the period or the stocks cannot be served by the published data |
| `LIMIT_EXCEEDED` | worker (`max_download_bytes`, `max_broker_rows`, `max_conditions`, `max_result_bytes`), edge-bff (result size) | too big |
| `DATA_MISSING`, `DATA_UNAVAILABLE`, `DATA_INTEGRITY` (424) | worker `terminal.ts`, page `live.ts` | no file, file unreachable, file not what its manifest says |
| `BUSY`, `QUEUE_FULL`, `SUBMISSION_CONFLICT`, `PREVIEW_REPLACED` | worker, edge-bff | concurrency rules |
| `TIMEOUT`, `WORKER_LOST`, `RESULT_NOT_STORED`, `RESULT_INVALID`, `OUT_OF_MEMORY` | edge-bff loop, worker | the job ended without a stored result |
| `RESULT_EXPIRED`, `RESULT_INTEGRITY`, `NOT_FINISHED`, `EVENTS_NOT_FOUND` | edge-bff result routes | reading a result |

Full list with HTTP statuses and page texts: CONTRACT.md section 11.

### 11.3 Who holds which secret

| Secret (variable name) | Held by | Used for |
|---|---|---|
| `TERMINAL_PUBLISHER_DATABASE_URL` | publisher | read-only market tables |
| `TERMINAL_BUCKET_*` (endpoint, region, name, key id, secret) | publisher (write), terminal-api | the bucket; never the worker, never the browser |
| `TERMINAL_DATABASE_URL` (`terminal_api_login`) | terminal-api | quotas and audit (schema `terminal`) |
| `TERMINAL_PROXY_KEY` | terminal-api, edge-bff; the workers (Railway reference) until theirs references their service key | the gateway account (TEMPORARY, decision U1) |
| `TERMINAL_SERVICE_KEY_BACKTEST_WORKER`, `TERMINAL_SERVICE_KEY_SCREENER_WORKER` | terminal-api; each worker's `TERMINAL_PROXY_KEY` references its own | the worker's service account (EXEC-MU-RUNTIME T1) |
| `BACKTEST_WORKER_KEY` | worker, edge-bff (reference) | edge-bff → worker calls |
| `EDGE_DATABASE_URL` (`edge_bff_login`), `EDGE_SESSION_SECRET` | edge-bff | sessions, CSRF, backtest tables |

Logs never carry these values, presigned URLs or database exception text (`failure_of` in edge-bff, `describeConfig`
in the worker, class names only in the publisher).

## 12. Operations

- **Environment**: Railway project with one environment, `dev`; there is no production yet.
- **Deploy sources**: edge-bff deploys from GitHub `main` (watch pattern `/apps/edge-bff/**`), so the page ships with
  it. backtest-worker, terminal-api and terminal-publisher are CLI uploads (`railway up`): merging to `main` does not
  redeploy them. ERRORS M252: a merge commit can be skipped by Railway ("No changes to watched files"); after every
  merge check the edge-bff deployment and deploy the commit explicitly when it was skipped. Ids and procedures:
  `RAILWAY_CHANGELOG.md` 2026-10-26 and 2026-10-27 entries.
- **Migrations**: `20261026_005` and `20261027_005`, applied in dev (DRYRUN then APPLY on orc-test-runner; logs in
  `verification/backtest/jobs/`).
- **Tests** (run one suite at a time; the edge-bff suite uses a cluster-wide role):
  - page: `npm run typecheck`, `npx vitest run`, `npm run smoke` in `apps/edge-bff/backtest`;
  - worker: `npm test` in `apps/backtest-worker` (`node --test` over `tests/*.test.ts`, with `tests/fake-terminal.mjs`
    imitating terminal-api and the bucket);
  - edge-bff: `EDGE_TEST_POSTGRES_URL=<disposable Postgres> python -m pytest -q` in `apps/edge-bff`
    (`tests/test_backtest.py`; Chromium tests need `EDGE_TEST_CHROMIUM`);
  - publisher: `python -m pytest apps/terminal-publisher/tests`; terminal-api: `python -m pytest -q` in
    `apps/terminal-api`.
- **End to end in dev**: `verification/backtest/e2e_dev.py` drives the real page through edge-bff, worker,
  terminal-api and the bucket (single run, its repeat, refusals, portfolio preview, 12-stock portfolio with
  reconciliation and robustness checks, cancel). `measure_dev.py` measures; `flow_data_check.py` checks broker flow
  in storage against SQL. Last full pass: 2026-10-27 13:27 UTC (single 5.31 s end to end, portfolio of 12 13.38 s).

## 13. Known open items

| Item | Status | Where |
|---|---|---|
| Files overwritten in place during publisher runs → `DATA_INTEGRITY` | FIXED in code (content keys + cleanup); dev verification PENDING: the first scheduled run with it (00:30 UTC 2026-10-28, `4c2c3823`) crashed in planning before the cleanup and before any write (ERRORS M263) | ERRORS M250, M263 |
| Database connection lost mid-write in edge-bff | cause UNKNOWN; retried until the deadline | ERRORS M246 |
| Merge deploy skipped by Railway | MITIGATED by hand; automatic check PROPOSED | ERRORS M252 |
| Terminal page download has no retry | not covered (the backtest page has it) | ERRORS M251 |
| Mixed adjusted/raw price history (2026-09-12) | warned; origin of the date unknown; fix belongs to the data layer | decision K4 |
| One shared gateway account and unlimited quota overrides | TEMPORARY for the page; the workers' own service accounts are in code (EXEC-MU-RUNTIME T1, migration `20261028_100`), active once their variables reference their keys | decision U1 |
| Broker data lags prices until a new Stockbit token | OPEN | ERRORS M243 |
| No delisted stocks, no historical index membership | warned (`SURVIVORSHIP`) | decision K6 |
| `backtest_jobs` rows and `backtest_trials` are never purged; `prior_trials` grows per lineage | no decision yet | `apps/edge-bff/README.md` |

## 14. How to change things

| Change | Files | Tests |
|---|---|---|
| Add or change an indicator | `terminal/src/data/indRegistry.json` or `terminal/src/calc/indicators.ts`, then `npm run registry` in `apps/backtest-worker` and commit `core/backtest-registry.json` (start-up and `registry:check` refuse a stale one) | `apps/backtest-worker/tests/registry.test.ts`, page vitest |
| Add a request field | core `contract.ts`, worker `validate.ts` `FIELDS` + `checkRequest`, page `api/request.ts`, CONTRACT.md section 3 | `validate.test.ts`, `run.test.ts` |
| Add a condition kind | core `conditions.ts` (+ `hash.ts` shapes for lineage and variant), page builder | worker engine and validate tests, page vitest |
| Change engine rules | core `engine.ts` (changes `engine_version` by itself), CONTRACT.md sections 4 to 6 | `apps/backtest-worker/tests/engine.test.ts`, the oracles |
| Add a dataset (macro, cross-asset) | publisher (SQL, document, stamp, `run`, `data_through`, `verify`), terminal-api `BundleRequest`/`/bundle`, worker `terminal.ts DATASETS` + core `datafile.ts` decoders + `load.ts` limits, page `live.ts` | publisher tests, `terminal.test.ts`, `load.test.ts`, keep `fake-terminal.mjs` in step |
| Add a limit or variable | worker `config.ts` (+ core `Limits` to show it in the catalog), edge-bff `config.py`, README tables, `.railway/railway.ts` | `server.test.ts`, edge-bff settings test |
| Add a public route | `Backtests.routes` (literal paths before `/{request_id}`), CONTRACT.md section 9 | `tests/test_backtest.py` |
| Change a table | a new forward migration with its `$verify$` block, `tests/conftest.py` list | migration tests in `test_backtest.py` |
| Change the page | keep markup and CSS 1:1 with `backtest.html`; `tests/visual` compares with the reference | vitest, `npm run smoke`, visual harness |

## 15. Where the time goes, and what could be faster

Measured (FACT) first, then the openings (INFERENCE unless stated).

- **Worker downloads dominate a cold run**: 12 stocks = 60 files, 28 MB, 6.1 s of 7.05 s. The worker is in `sfo` and
  the bucket in `sin` (2.3 s median per file download); moving the worker to `sin` made downloads faster but every
  terminal-api call slower (catalog 22 s), so it stays in `sfo`. Openings: a bucket region next to the services, or
  fewer and larger files for the broker years still yearly.
- **Warm runs are CPU-bound**: 5.5 s warm for 12 stocks; caches hold gzip bytes, so each use re-hashes, inflates and
  decodes. Opening: a decoded-series cache keyed by sha256 in the worker.
- **Catalog**: with flow on, one `/manifest` per stock (about 845 terminal-api requests, each with a database
  transaction) plus both reference files on every build (2.3 s; edge-bff caches 60 s). Opening: a coverage field in
  `state.json` written by the publisher, read once.
- **Reference files** are downloaded again by every validation, preview and job (no sha256 to cache them by).
  Opening: publish them with a sha256 (or content keys) and cache them like data files.
- **Page**: one `/bundle` per dataset per ticker (two for a flow ticker), each with a session lookup that opens a new
  PostgreSQL connection in edge-bff (`Store.connect`, no pool). Openings: ask both datasets in one `/bundle`
  (terminal-api accepts several); a connection pool in edge-bff.
- **edge-bff result route**: single mode gunzips, merges and re-gzips the result on every read. Opening: store the
  merged single-mode part once at ingest.
- **Publisher**: sequential, about 1.4 s per object written; planning reads up to 845 manifests one by one. Openings:
  parallel manifest reads or one index object; assembling the price pack from the yearly rows already read.
- **Monte Carlo and statistics** have no cancel check; a cancel waits for them (`run.ts`).

## 16. Glossary

- **Manifest**: the per-ticker JSON that lists each published file's key, sha256, bytes, rows and dates.
- **Pack**: one file holding several years (price: all years; broker archive: all but the last two).
- **Bundle**: terminal-api's answer with presigned URLs for one ticker's files.
- **Lineage key / variant hash**: the strategy line trials are counted in / one exact variant of it.
- **Trial**: a distinct variant evaluated on a line; feeds the deflated Sharpe.
- **WIB**: UTC+7 (the publisher runs at 07:30 and 19:00 WIB = 00:30 and 12:00 UTC).

## 17. EXEC-BACKTEST-LOAD (2026-10-27): the page loads like the Terminal

User 2026-10-27: "Agar waktu loading bisa sama. Seperti bagian terminal." Measured from the sandbox with
`verification/backtest/page_timing_dev.py` (MAPI, BBRI) before and after, the Terminal measured the same way:

| | Before | After | Terminal |
|---|---|---|---|
| first open, until the menus and Run are usable | 8.83 s | 1.37 s | chart 2.28 s |
| second open | 2.36 s | 1.12 s | chart 1.77 s |
| catalog (worker `/v1/catalog`) | 3.5–4.0 s on every build | about 0.25 s (kept per publication) | — |
| longest main-thread block (open; switch to BBRI) | 0.53 s; 0.97 s | none over 50 ms | — |

What changed: terminal-api `GET /state`; the worker's catalog and reference lists per publication (`ByPublication`,
built at start); the page draws at once (`PROVISIONAL`, loading lines), candles before broker data, one `/bundle` per
ticker, decoding in `api/load.worker.ts`; one rack module for both pages' cache and downloads
(`terminal/src/data/rack.ts`); a connection pool in edge-bff (`app/store.py`). Still open: the run itself (5–13 s),
the publisher's in-place rewrites (M250).
