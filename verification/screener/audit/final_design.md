# EDGE Screener: final recommended design (judge's synthesis, 2026-10-27)

## How to read this document

**Labels.**
- **FACT**: cited from code, data or a recorded measurement.
- **INFERENCE**: reasoned from facts.
- **PROPOSED**: a design choice.
- **UNKNOWN**: not established.

**Evidence.**
- The audits are in `/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/results/`. Where the four verifications refute an audit, the verification wins.
- Raw evidence is under `.../scratchpad/audit/`.
- Repository HEAD is `641e55e`. The audits ran at `3db84ae`; the only later commit adds ERRORS D22/D23.
- Nothing in the repository, the database or Railway was changed.

**My own read-only checks in this pass** (all FACT):

| Check | Finding |
|---|---|
| Live `has_table_privilege` | `terminal_market_reader`, `terminal_publisher_login` and `terminal_api_login` can SELECT Price, F05, `idx_event_annotation` and `IDX_Stock_Universe`. None of them can SELECT F03, F04, F06, `Monitoring_Stockbit_Update` or `Monitoring_Price_ALL`. `edge_bff_runtime` reads none of these. `market_ai_sql_reader` reads Price, F03 and F04, but not F05 or F06. |
| `pg_auth_members` | Both `terminal_publisher_login` and `terminal_api_login` are members of `terminal_market_reader`. |
| `scripts/provision_terminal_logins.py:15-31` | Each login must reach exactly its listed relations, or provisioning rolls back. So a grant to `terminal_market_reader` also widens `terminal_api_login`. |
| `apps/terminal-publisher/publisher.py` | `:17-18`: publisher runs at 07:30 and 19:00 WIB, decided by the user on 2026-10-26. `:549-554`: `state.json` holds `price_through`, `broker_through`, `broker_behind_sessions`, `finished_at`. `:55-57`: `PRICE_SQL`. `:63-66`: a full `PRICE_STAMPS_SQL` GROUP BY on every run. |
| `apps/terminal-api/app/main.py` | Routes: reference, logo, manifest, files, bundle, history, admin. There is no `/state` yet; it is planned in `PLAN.md:924-929`. |
| `apps/edge-bff/app/main.py:34-36` | The browser gateway allow-list. |
| `PLAN.md:902` | The user, on the Backtest page: "Idealnya sih kalau ini menggunakan satu source ... harusnya ya sama aja sih prosesnya dengan terminal." |
| `Monitoring_Stockbit_Update`, newest rows | SUCCESS 14:28-14:53 UTC with `broker_dates` []. A stale RUNNING row from 14:25. FAILED at 14:18. SUCCESS 11:08-12:58 with ["2026-10-26","2026-10-27"]. |
| `apps/backtest-worker/src/version.ts:18-21` | `engine_version` hashes `apps/edge-bff/backtest/src/core/*.ts|json` and `apps/backtest-worker/src/*.ts`. |
| ERRORS entries | M250 (`ERRORS_AND_SOLUTIONS.md:2617-2660`; user chose fix A, content-addressed keys) and D22/D23 (`:188-189`). |

## 0. Verdict

**Winner: the reliability design**, used as the spine. Its invariants hold in the final design:
- **I1 One formula path.** Every technical number is `F[key]` through `Calc.out(key, resolveParams(...))`. There is no SQL, TA-Lib or prototype `XI` copy.
- **I2 One bar snapshot per screen**, from the same rack publication the Terminal and Backtest read.
- **I3 Backtest untouched.** No byte changes in `indicators.ts`, `indRegistry.json`, `backtest-registry.json`, `backtest/src/core/**` or `apps/backtest-worker/**`, enforced by a tripwire test.
- **I4 Feature 04 unchanged.** It is a parity oracle only.
- **I5 Nothing fabricated.** Every value is PASS, FAIL or NA, and every NA carries a reason.
- **I6 Versions in every response.**
- **I7 No silent adjustment.** Invalid input is refused; it is never clamped or reordered.

Grafts, where they are better supported than the reliability design's own choice:
- **From the performance design:** the content-addressed cross-sectional rack files and the flow computed from a published F05 window with `flow.ts`. Also performance mechanics: partial caches, the result cache, near rows always computed, the cost budget and the bit-parity gate.
- **From the simplicity design:** the thin client, with a server-computed preview pinned to `data_version`. Also a dedicated reader group instead of widening an existing role, sidecar fields such as `price_compare_lag` and `level_comparable`, and caps derived from a measured cost rule.

### Contradictions resolved (PROPOSED)

| # | Topic | Options proposed | Resolution and evidence |
|---|---|---|---|
| C1 | Price data source | Reliability: per-ticker rack packs. Performance: a separate 10:20 UTC screen cron. Simplicity: a direct DB login. | **Rack cross-sectional files written in the same publisher run as the Terminal and Backtest data.** The user wants one source (`PLAN.md:902`) and chose the rack schedule (`publisher.py:17-18`). Per-ticker refresh costs 845-1,690 grants and audit rows per publication and depends on the TEMPORARY gateway override (benchmark.md §4; CONTRACT [D-U1]). A DB login adds a credential and re-reads on every restart, and both other options create a second time base. Freshness becomes a rack-wide decision (P1). |
| C2 | Preview data | Reliability: browser `/bundle` plus a browser recompute. Simplicity and performance: worker-computed. | **Worker `POST /preview` pinned to `data_version`.** The page carries no formula code, needs no drift check or ulp tolerance, makes no grant per click, and page/worker skew cannot change a number. |
| C3 | Flow ranking | Reliability: a SQL Feature_07 table (Phase 3). Performance: a published F05 window plus `flow.ts`. Simplicity: a DB grouped read in the worker. | **Published F05 window plus `flow.ts`.** There is one top-N formula, `top5Accumulation` (`flow.ts:108-119`), and no stockbit-updater coupling (verify_flow additional findings). A governed Feature table is revisited only if the AI needs these metrics. |
| C4 | Grant target for the publisher | Performance: `terminal_market_reader`. | **A new NOLOGIN group granted to `terminal_publisher_login` only.** `terminal_market_reader` also serves `terminal_api_login`, and the provisioning script checks exact reach. |
| C5 | Near-miss pruning | Reliability: prune by toggle. Performance: always keep near rows. | **Always compute near rows.** The toggle becomes local; pruning ALL screens at the second failure is cheap (0.35-0.56 s for an exhaustive 3-condition screen). |
| C6 | `rs_rank` population | Performance: the filtered universe. Reliability and simplicity: a fixed population. | **Fixed:** active, non-stale stocks with a finite value on E. Ranks do not move with filter edits and stay planner-safe. Product decision P7. |
| C7 | Response shape | Performance: columnar. Others: rows. | **Rows, gzip.** Columnar saves about 13 KB gzip at 845×5 (37.1 vs 23.6 KB, benchmark.md §2); rows keep the UI port and CSV simple. |
| C8 | Screener core location | Simplicity: `apps/screener-worker/src/core`. | **`apps/edge-bff/screener/src/core`.** It sits outside `backtest/src/core`, so `engine_version` is unchanged, and the page can import `contract.ts` and `universe.ts` (edge-bff build context is `/apps/edge-bff`, `railway.ts:182`). |
| C9 | Where top-N generalises | Simplicity: in `flow.ts`. | **In screener core.** A change to `flow.ts` changes the Backtest's `engine_version`. |
| C10 | Brief: "Do not rebuild all historical indicators every day" vs an in-memory recompute per publication | — | **The screener writes nothing.** The recompute costs 8.1-10.2 s CPU per publication (benchmark.md §2d). Making it incremental and exact needs streaming state per indicator, the same double implementation that rules out Option A (feature04.md §11). Recorded for the user in P2. |
| C11 | Maximum `within` | 130 vs 120 | **130 sessions**, the prototype's own marker window (html_model.md §4.2). Flow maxima are derived from the published window length. |

## T1. Where screening computation runs

**Decision (PROPOSED).**
- A new private service, `screener-worker`:
  - Node 22 with type stripping and the backtest worker's `loader/register.mjs`.
  - No npm runtime dependency.
  - 1 replica in `sfo`, private networking only.
  - No Postgres or bucket credentials.
  - Reads the rack through terminal-api with the gateway proxy key, as backtest-worker does (CONTRACT.md §1).
- Pure screener code lives in `apps/edge-bff/screener/src/core/`.
- edge-bff relays through a new `app/screener.py`.
- The browser renders only.

**Evidence and rejections.**
- **Inside backtest-worker: rejected.**
  - FACT: `engine_version` hashes every file in `backtest/src/core` and the worker's `src` (`version.ts:18-21`), and it enters every Backtest request hash (`hash.ts:131-132`). Any screener file there would silently change every Backtest result key.
  - FACT: the worker has 2 compute threads, runs one preview at a time, caps runs at 12 tickers (`engine.ts:151`) and peaked at 1.31 GB in its worst case (reuse.md §1.2, §3.2).
- **Inside edge-bff: rejected.** FACT: `uvicorn --workers 1` (`railway.ts:184`); its runtime role reads no market table (live query). Python also cannot run `F`.
- **In the browser: rejected.** It breaks the hard constraint, needs 845 `/bundle` calls, and default quotas allow 30 tickers/h (benchmark.md §4).
- **SQL or a Python/TA-Lib engine: rejected.** It would be a second formula implementation. FACT: TA-Lib's MACD, CMO, STOCHRSI fastk and PPO differ from `F` (matrix_a pattern 3), and 42 of the 53 indicators have no Feature 04 code (verify_feature04 F04-17).
- **The cost is small.** FACT: one custom indicator over the whole universe on full history takes 80-250 ms on one thread; three conditions take 354-564 ms; all 53 defaults take 8.1-10.2 s; peak RSS is 299 MB (benchmark.md §2).

**Threads (PROPOSED).**
- A `worker_threads` pool. It starts with K=2; Phase 17 sets K.
- The snapshot is built on a builder thread while the old version keeps serving.
- Bars live in SharedArrayBuffer-backed Float64Array columns only after a bit-parity test of `F` on typed views against plain arrays (53 indicators × 50 tickers). If that test fails, each thread holds its own copy.

**Deploy (PROPOSED; decision P15).**
- GitHub `main`, root `/`, `dockerfilePath apps/screener-worker/Dockerfile`.
- watchPatterns: `/apps/screener-worker/**`, `/apps/edge-bff/screener/src/core/**`, `/apps/edge-bff/backtest/src/core/**`, `/apps/edge-bff/terminal/src/calc/**`, `/apps/edge-bff/terminal/src/data/indRegistry.json`, `/apps/backtest-worker/src/terminal.ts`.
- Precedent: feature-04-worker (`railway.ts:162-169`).
- Check the deployment for each merge commit (M252).

**Class and layer.** This is a CPU-bound cross-sectional compute service over the rack. Future macro or cross-asset screens add a file family, not a service. The mechanism belongs to the service contract plus the pure core.

**Covers:** every screen and the preview. **Does not cover:** AI access to screener values, which needs a later onboarding per NEW_TABLE_ONBOARDING_PLAN.

**Risk and cost:** one Railway service. Memory INFERENCE is 0.5-1 GB, measured in Phase 17.

**Verification:**
- The tripwire `scripts/screener/check_backtest_untouched.mjs` asserts `engineVersion()` and `REGISTRY_VERSION` equal those of `origin/main`.
- The backtest-worker `npm test` and `registry:check` stay green.
- A load test runs screens during a Backtest job; the job's duration must stay unchanged.

**Permanent.**

## T2. Market data path, data version, freshness and as-of policy

**Decision (PROPOSED): one source, the rack publication.** A new content-addressed cross-sectional file family:
- Key: `v1/xsection/<name>.<sha16>.json.gz`.
- Written by the existing terminal-publisher in the same `daily` run, at 07:30 and 19:00 WIB.
- Written before `state.json`, which gains an index `xsection: {name: {key, sha256, bytes, rows, as_of}}`.

terminal-api gains two routes:
- `GET /api/terminal/v1/state`: no quota, no audit row. It is the same route BACKTEST-LOAD K1 plans (`PLAN.md:924-929`), so both features share one mechanism.
- `POST /api/terminal/v1/xsection {names}`: presigned URLs, 1 audit row, file quota = n.

Neither route is in edge-bff's browser allow-list (`main.py:34-36`), so the browser can never pull these files.

**Phase 1 files.**
- `price`: every ticker including IHSG, full history from `price_first_year`, in the existing pack encoding, plus each ticker's published pack sha256.
  - Built from one bounded statement, `PRICE_SQL` without the ticker filter. A seq scan of 1.33 M rows takes about 2.0 s server-side (reuse.md §3.4 E).
  - Alternatively, built from the pack documents the run just produced.
  - A publisher unit test asserts that each per-ticker xsection document equals its pack document.
- `ref`, from `IDX_Stock_Universe`, which the publisher already reads (`publisher.py:111-112`):
  - name, type, sector, industry, first and last bar;
  - price-affecting corporate actions with an ex-date on or after `ADJUSTED_HISTORY_BOUNDARY` (`engine.ts:157`; `PRICE_ACTION_TYPES`, `datafile.ts:236`);
  - cash dividends of the last 6 years.

**Worker refresh rules.**
- Poll `/state` every 60 s.
- When `finished_at` changes:
  1. Download the named files with `TerminalClient.file` and `inflateVerified`, which checks sha256 and size (`datafile.ts:91`).
  2. Decode each ticker through `priceSeries` (`datafile.ts:139`), so the Terminal and Backtest bar rules apply.
  3. Cross-check every listed pack sha256 against `/manifest`: no quota, about 2.3 s for 845 tickers (benchmark.md §4).
  4. Build the next snapshot, then swap all-or-nothing. Any integrity failure keeps the previous version, logs `REFRESH_FAILED` and retries with backoff.
- Never build during a run. Old content-addressed objects survive until the next run, so a restart mid-run reads the previous index safely.

**M250.** INFERENCE: the new family is immune to M250 by construction. It is the first application of the user's chosen fix A (`ERRORS_AND_SOLUTIONS.md:2655-2657`) and does not wait for the general PR.

**Versions and freshness.**
- `price_data_version` = `datafile.dataVersion` over (ticker, `price`, pack sha256) (`datafile.ts:271`). This has the same meaning as the Backtest's data version, so a Send-to-Backtest handoff can say whether both run on the same data.
- Every response carries `price_through`, `broker_through`, `broker_behind_sessions` and `published_at` (= `finished_at`) (`publisher.py:549-554`).
- Feature 04 `calculated_at` is not used: Feature 04 is not on the path.

**As-of policy.**
- Evaluation date E = `price_through`.
- Each ticker is evaluated at its own last bar on or before E. FACT: the Backtest does the same, with no filling (CONTRACT §2).
- **STALE** = last bar before E. FACT: 16 stocks today, ADHI (2026-08-21) through MSIN and TGKA (2026-10-26) (feature04.md §8). They are excluded by a visible default chip and flagged when included (decision P4).
- `bars_ago` counts the ticker's own bars. `market_sessions_ago` is informational: FACT, the 2026-09-17/18 sessions are missing for every stock (M238; verify_feature04 F04-06).

**History.** Always the full published history. FACT:
- cumulative series never converge;
- EMA200 is up to 7.7% off with 500 bars;
- KAMA on BABP is still 1.3e-3 off with a 1,000-bar tail (verify_matrix_a; verify_matrix_b).

**Freshness consequence.**
- FACT: between the price cron (10:00 UTC, `railway.ts:93`) and the end of the 19:00 WIB publication (about 13:03 UTC, M250), the database holds a session the rack does not, about 3 h on each trading day.
- The screener shows exactly what the Terminal and Backtest show.
- Fresher data for everyone is a rack schedule decision (P1). A screener-only early build is not offered.

**Rejected.**
- Reliability's per-ticker refresh as the primary path (benchmark.md §4):
  - 845-1,690 grants and audit rows per publication on one subscriber lock;
  - a cold load of 50 s to 2.5 min;
  - a dependency on the TEMPORARY 1e9 override.

  It is kept only as a TEMPORARY fallback adapter if P1(b) is chosen.
- Performance's 10:20 UTC screen cron: a second data version and an override of the user's schedule.
- Simplicity's DB login:
  - a credential in a compute service, against the CONTRACT §1 pattern;
  - a full read per version and per restart on `shared_buffers` of 128 MB;
  - the same second time base.

**Quota.** FACT/INFERENCE: about 2-4 files per publication fit the default quotas (files_per_hour 60, megabytes_per_day 300; migration `20261025_100:79-83`). The design does not depend on the TEMPORARY override.

**Class.** Every whole-universe reader of the rack, including future macro and cross-asset data, uses one file family and one state route. The mechanism belongs to the data layer (publisher), the service contract (terminal-api) and the consumer (worker).

**Covers:** price, universe and corporate-action data. **Does not cover:** flow (T8) and historical as-of dates (T10).

**Risk and cost:**
- A publisher run gains about 14 MB of upload (INFERENCE, from the 14.22 MB of pack gzip) and one 2 s scan.
- There are CLI deploys of the publisher and terminal-api.
- Coordinate with BACKTEST-LOAD on `/state`.

**Verification:**
- A pack-sha cross-check on every load.
- A fixture where one entry's sha256 is corrupted: the swap must abort and the old version keep serving.
- The version must not change across a reload with identical data, and must change when a fixture changes one bar.

**Permanent.** The per-ticker fallback is TEMPORARY.

## T3. Feature 04 strategy

**Decision (PROPOSED): Option B, strict form.**
- Feature 04 is unchanged: no column, VERSION, checkpoint, worker or migration change.
- The screener does not read Feature 04 at runtime.
- The precomputed default layer is the in-memory snapshot computed by `F` once per publication (T4).

**Feature 04 roles.**
1. **Parity oracle** in tests. A pinned parity record pairs `registry_version` with the Feature 04 VERSION.
2. **Optional continuous reconciliation** (Phase 2): an `f04` xsection file holding the latest equity cross-section, about 828 rows, read in 2-84 ms (benchmark.md §3). It needs a SELECT grant on F04 to the publisher group (T16). The worker logs mismatch counts and never alters results.
3. **AI consumer**, unchanged: 49 allowed columns and 57 calculation rows (feature04.md §7).

**Why Feature 04 is not a runtime source.**
- **No precision gain.** FACT: `F` on full history equals the 15 stored columns for 828 rows, max relative difference 1.16e-15 (benchmark.md §2f).
- **Small coverage.** FACT: it serves only 9 of 53 indicators fully and 2 partly, and stores no OHLV (verify_feature04 F04-17 and additional findings).
- **No material efficiency.** INFERENCE: reading it saves about 1.5 s of the 8-10 s CPU per publication.
- **Two time bases.** FACT: Feature 04 finishes at 10:09 UTC, the rack at about 13:03 UTC.
- **Repair coupling.** FACT: the planned 2026-09-17/18 refill would put about 840 tickers into `REPAIR_REQUIRED` (verify_feature04 additional findings).
- **No grant.** FACT: no terminal role can read Feature 04 (live query).

**Option A (extend Feature 04): rejected.** FACT (feature04.md §11; verify_feature04 F04-14, F04-18):
- every indicator implemented twice, as the TA-Lib engine plus streaming checkpoint state;
- a VERSION bump invalidates 6,076 checkpoints;
- a rewrite of 1.39 M rows onto a heap about 4× bloated;
- the `_INDEX` table and catalogs, the stockbit-updater copy and three more writer scripts must change in step;
- `backfill.py` and `bootstrap_states.py` abort at IHSG.

**Option C (persisted screener table): rejected.** It needs a writer credential, a migration and catalogs to store values recomputable in seconds.

**Brief tension.** The brief expects "defaults from precomputed data" and says not to "rebuild all historical indicators every day". The screener persists nothing and recomputes 8.1-10.2 s CPU per publication. Exactness for recursive and cumulative indicators forbids tail windows (T2), and incremental exactness needs checkpoint state. This needs the user's acknowledgment: P2.

**Feature 04 items raised separately** (not screener scope; each needs its own approval):
- ERRORS entries for the refill → `REPAIR_REQUIRED` storm and for the IHSG abort in `backfill.py` and `bootstrap_states.py`.
- PBSA and FORU are already covered by D22.

**Verification:**
- Snapshot vs Feature 04 on all equity tickers at a common date: 15 columns plus 5 derivations (%B, bandwidth, NATR, stddev, PPO line) with `NULLIF(...,0)` denominators; relative difference ≤ 1e-12 and identical nulls.
- A perturbed fixture must fail the test.

**Permanent.**

## T4. Precomputed default path

**One path (PROPOSED).** A single function, `series(id, params, output)`:
- **Key:** (`price_data_version`, `screener_engine_version`, id, `canonicalJson(resolveParams(BY_ID[id], params))` (`hash.ts:12`), output).
- **On a miss:** `Calc.out(key, params)` on full history; keep a 131-bar tail per ticker plus `last_valid_index`.
- **Precomputed and dynamic are one call made at two times,** so they cannot differ. The cell's `source` reports `precomputed` (pre-warm hit) or `dynamic`.

**Pre-warmed at each publication:**
- all 53 indicators at registry defaults, 76 outputs (benchmark.md §2d; memory 76 × 845 × 131 × 8 B ≈ 67 MB, arithmetic);
- every configuration referenced by the presets, read from `presets.json` at run time;
- contract-declared derived series computed on the full series and then tailed: Donchian prior band, Bollinger-width rolling minimum, MA of an output;
- universe attributes: last close, previous close, 1D %, ADV20 = `signals.ts liquidity` (FACT `:176`, SMA20 of close × volume, the Backtest definition), first and last bar, bar count, stale flag, corporate-action flag;
- default cross-sectional ranks;
- every preset's match and near counts.

**On demand:**
- custom parameters, only for the tickers the planner keeps (T7);
- partial per-ticker entries are allowed;
- an LRU bounded by `SCREENER_CACHE_BYTES`, dropped on a version swap.

**Result cache:** keyed by `data_version`, engine version and `definition_hash`, holding gzip response bytes.

**Never precomputed or never offered:**
- Raw level thresholds on OBV, PVT, A/D, NVI and PVI. FACT: their level depends on the start bar forever, up to about 96,800% for NVI (verify_matrix_b). They are offered only as change, ratio, N-bar high and level vs own SMA with an explicit tie rule. EMA-based level states are computed on full history and labelled.
- Lengths above the caps (T5).
- Past evaluation dates (T10).

**Oracle mapping** (FACT, verify_feature04 F04-17; verify_matrix_a I17; verify_matrix_b I33). Values are equal only on full history.

| Indicator | Oracle |
|---|---|
| I01 SMA | `sma_20`, `sma_50` |
| I02 EMA | `ema_12/26/50/200` |
| I06 MACD | 3 outputs |
| I07 ADX | ADX output only |
| I13 RSI | `rsi_14` |
| I27 Bollinger | `bb_*_20` |
| I30 ATR | `atr_14` |
| I28, I29, I31, I32, I25 | derived: %B, bandwidth, NATR, stddev = (upper − basis)/2, PPO line |
| I35, I37 | Feature 01 `volume_avg_20d`, `volume_ratio_20d` |
| I17 | Feature 01 `return_{5,20,60}d_pct`, exact |
| I33 | no oracle: Feature 01 volatility is a different formula, median 2.8% and max 23% apart |

IHSG values are in `_INDEX`.

**Auditability:** a `snapshot_digest` (sha256 over every default tail) is logged per version.

**Verification:**
- For all 53, explicit default parameters equal the snapshot bit for bit and produce the same key.
- RSI(7) dynamic equals a direct `F.rsi` call.
- Evaluating on the tail equals evaluating on the full series for every bar of the tail. This holds because `compare` reads only `i` and `i−1` (`conditions.ts:52-61`).

**Permanent.**

## T5. One approved indicator contract (Phase 4)

**Existing chain** (FACT): workbook → `indRegistry.json` + `indicators.ts` `DEFAULTS`/`F` → `build-registry.mjs` → generated `backtest-registry.json`, which carries `registry_version` = sha256(`indRegistry.json` + `indicators.ts`)[:16]. The worker exits on a mismatch (`server.ts:342-343`). `scripts/terminal_indicator_spec.py` generates the AI formula reference, including the `feature04` mapping.

**Decision (PROPOSED).**
- **Do not edit `indRegistry.json` or `indicators.ts` now.** Any byte change bumps `registry_version`, and the CLI-deployed worker stops until it is rebuilt (verify_matrix_b additional findings).
- **Generated `apps/edge-bff/screener/src/core/screener-registry.json`** is built by `apps/edge-bff/screener/scripts/build-screener-registry.mjs` (with `--check`) from three inputs:
  1. The base `backtest-registry.json`, unchanged. It stays the only contract for ids, keys, parameters, types, defaults, min/max/options, `not_accepted` and outputs.
  2. A hand-kept `screener-overlay.json` holding only fields that exist nowhere else:
     - `shape`;
     - allowed tests per output;
     - `level_comparable`;
     - `price_compare_lag` (1 for I10 Donchian; FACT, same-bar `close > upper` never fires, 0 hits vs 29,041-54,652 with the prior-bar form, verify_matrix_a);
     - narrowing: I09 `factor > 0` (FACT, factor 0 gives 1,128 flips on BBRI), `annualization_periods` integer (FACT, floored silently), I37 `include_current_bar` hidden (its label contradicts `F`), VWMA basis hidden for IHSG;
     - display unit;
     - the `f04`/`f01` oracle mapping;
     - `cost_class` (O(N) or O(N·n)) with measured ns per bar;
     - `history_class` (window, recursive, state, cumulative, calendar).
  3. Fields derived from code at build time:
     - `first_valid_bar` per output, by running `F` on a deterministic series;
     - **caps**, derived by the rule "full-market cold compute at the cap ≤ `SCREENER_CAP_BUDGET_MS` on one thread" from `cost_class` and the measured ns per bar. FACT inputs: CCI(1000) 7.93 s; O(N) kernels ≤ 0.09 s at n=1000 (verify_matrix_a).
- **Narrow-only rule:** the overlay may only narrow the base. Every transferable screener condition is therefore Backtest-valid.

**Versions:**
- `registry_version` is passed through.
- `screener_registry_version` = sha256(base + overlay)[:16].
- `screener_engine_version` = a content hash over screener core, worker `src`, the imported core and calc files, and the Node major version (the `version.ts` mechanism).

**Consumers:**

| Consumer | Reads |
|---|---|
| Worker | the generated file; refuses to start on mismatch |
| Page | only `/catalog`; `XPARAM` is deleted |
| Backtest | unchanged |
| Feature 04 Python | unchanged; linked by a test |
| AI catalogs | unchanged now |

**New indicators** (Ichimoku and any other not in the 53) go into `F` and `indRegistry.json` through a deliberate registry release with a worker rebuild (P6), never as screener transforms.

**Drift tests:**
1. `--check` on the generated file.
2. Start-up hash check.
3. One overlay entry per base id, and vice versa.
4. Narrow-only assertions.
5. History-class start-dependence: cut at bar 1000; window class must be equal, recursive and cumulative unequal.
6. Python: every oracle column exists in `features/feature04/engine.py COLUMNS` and matches `terminal_indicator_spec.py`.
7. Pinned parity record in `verification/screener/F04_PARITY.md`.

**Class:** derived metadata copied by hand, as with `XPARAM` and the I37 label. **Layer:** catalog metadata as a generated artifact.

**Permanent.** Folding the overlay into `indRegistry.json` is a later planned registry release.

## T6. Condition engine (Phase 8)

**Wire grammar (PROPOSED).**

Metric reference:
- `{kind:'indicator', indicator, params, output}`
- `{kind:'price', field}`
- `{kind:'transform', fn: pct_distance|band_position|lag|change|rolling_max|rolling_min|ma|ratio|vs_index, of, args}`. These are condition arithmetic over `F` outputs and the exported `sma`/`ema`/`rma`, not formulas.
- `{kind:'pattern', type: breakout|breakdown|volspike|macross|macd_divergence|squeeze}`, reusing `PRICE_ACTION`, `priceActionCondition` and `bullishDivergence` (`conditions.ts:124-190`).
- `{kind:'flow', metric, params:{window, board}}`
- `{kind:'xsection', metric:'return_rank'}`
- `{kind:'universe', attr}`

Tests:

| Kind | Rule | Returns |
|---|---|---|
| **VALUE** | `gt`/`lt` strict; `between` inclusive and counted as one condition; `value > value2` refused with `INVALID_CONDITION` (the prototype silently reorders, html_model §4.1; documented UX change, and the UI validates first) | `value`, `unit`, `eval_date` |
| **STATE** | `compare(lhs, op, rhs)[at]`, lhs and rhs from price, an output, a value or a second instance (SMA50 vs SMA200) | `pass`, lhs, rhs, `eval_date` |
| **EVENT** | `crosses_above`/`crosses_below` through core `compare` (bar 0 never true, NaN false, both sides finite on the previous bar), or a pattern signal; `within` N from 1 to 130; j = largest index in [at−N+1, at] where the signal is 1 | `event_date = dates[j]`, `bars_ago = at−j`, `market_sessions_ago`, current lhs and rhs, `last_event_date` within 130 bars |

An event is never reduced to a state. `combineEntry` is deliberately not used: FACT, its single window turns states into "true on any of the last W bars" (`conditions.ts:269-292`).

**NA reason codes** (per cell; never fail the screen):

| Code | Meaning |
|---|---|
| `INSUFFICIENT_HISTORY` | the core's `INDICATOR_OUTPUT_EMPTY` (`conditions.ts:100`), caught per ticker with the `EXCLUDED_CODES`/`unlessLeftOut` pattern |
| `NULL_AT_EVALUATION` | zero width, flat window, zero volume, IHSG volume |
| `STALE` | last bar before E |
| `FLOW_UNAVAILABLE` / `FLOW_LAGGED` | flow missing, or later than the policy allows |
| `NOT_APPLICABLE` | scope excludes the ticker |

A metric with no data at all is refused at validation with `METRIC_UNAVAILABLE`, so the UI shows it disabled.

**Match.**
- `need = entryNeed(logic, at_least, active)` (`conditions.ts:263`; equal to the prototype's `needOf`).
- `met` counts PASS only.
- **One near rule for table, preview and CSV:** `near = !match && need ≥ 2 && met == need − 1`. This fixes the prototype's second rule at line 1599 (html_ui.md §3.15).
- `na_count` is returned.

**Sort.**
- Default order: match, then met, then ADV20 descending, then ticker ascending. FACT: market cap does not exist (fundamentals_universe.md §4).
- Per-cell sort key: the value for VALUE and STATE, `1000 − bars_ago` for EVENT.
- Nulls go last in both directions.

**`rs_rank` (P7).**
- Population: active, non-stale stocks with a finite value at E, fixed before conditions.
- `pct = 100·#(strictly lower)/(P−1)`; NaN excluded (fixes prototype defect 9); ties share a rank.
- IHSG alignment through `asOf` (`datafile.ts:259`).

**Floating ties.** Raw doubles, no epsilon: identical to the Backtest. FACT: on flat windows running-sum residue decides ties (BNBR, 358 of 358). The mitigation is the liquidity and traded filters; a global tie rule would be a later core release.

**Reused unchanged:** `F`, `DEFAULTS`, `sma`, `ema`, `rma`, `isN`, `REGISTRY`, `BY_ID`, `resolveParams`, `Calc`, `compare`, `PRICE_ACTION`, `priceActionCondition`, `bullishDivergence`, `entryNeed`, `switchOns`, `liquidity`, `EXCLUDED_CODES`, `inflateVerified`, `priceSeries`, `brokerRows`, `corporateActions`, `asOf`, `dataVersion`, `flowData`, `brokerNet`, `rollingSum`, `top5Accumulation`, `TerminalClient`, `catalog.ts` `regToCondition`/`legacyToCondition`/`DISPLAY`.

**New pure code** in `apps/edge-bff/screener/src/core/`:

| File | Role |
|---|---|
| `contract.ts` | wire types |
| `validate.ts` | refusals naming the field, the allowed values and the fix (the AGENTS gate rule) |
| `registry.ts` | loads the generated registry |
| `metrics.ts` | reference → series |
| `transforms.ts` | condition arithmetic |
| `evaluate.ts` | VALUE, STATE, EVENT at `at` |
| `match.ts` | match, near, counts |
| `plan.ts` | T7 |
| `xsection.ts` | cross-sectional ranks |
| `flowmetrics.ts` | flow metrics, including `topNAccumulation` |
| `universe.ts` | universe filters, shared with the page |
| `presets.json` | presets |
| `to-backtest.ts` | T12 |

**Legacy prototype metrics map onto the registry** (P6):

| Prototype | Mapping |
|---|---|
| `price_ma` | I01/I02 + `pct_distance`; EMA uses `F`'s SMA seed |
| `ma_cross` | cross-instance state or event |
| `rsi`, `stoch`, `macd`, `adx` (+DI/−DI from I07), `bb`, `atr` (I31), `supertrend` (I09 direction) | registry indicators |
| `breakout` | core `breakout` |
| breakdown | new pattern on Donchian lower lag 1 |
| `volspike` | core `volspike` (previous-N mean) |
| `hi52`, `lo52` | `rolling_max`/`rolling_min` 250 |
| `ret` | I17 |
| `rs` | `vs_index` |
| `squeeze` | bandwidth ≤ `rolling_min` |
| `silent` | transform pattern |
| `ichimoku` | requires a registry release |

**Verification:**
- gt, lt and crosses equal the Backtest's `conditionSeries[at]` on 200 tickers.
- `between` at value = min and value = max.
- Within boundaries: N−1 bars ago passes, N fails.
- Bar 0, NaN, a missing previous bar.
- State ≠ event: a state true for 10 bars with no cross in N must FAIL the event.
- Donchian prior band ≡ `breakout`.
- Every NA code, including RANS with 74 bars and IHSG volume.

**Permanent.**

## T7. Query planner (Phase 7)

**Stages (PROPOSED):**

| Stage | What it evaluates | Note |
|---|---|---|
| S0 | universe hard filters: stocks, sector/industry in and out, price, ADV, traded on E, corporate-action exclusion, history length, explicit tickers, universe metric filters | conjunctive, outside `met`, safe for every logic |
| S1 | population-level cross-sectional values (`rs_rank`) on the fixed population | never pruned |
| S2 | snapshot lookups | O(1) per ticker |
| S3 | dynamic conditions ordered by predicted cost (overlay `cost_class` × length × survivors' bars, calibrated by an exponentially weighted mean of measured ms) | |
| S4 | completion pass over every remaining cell of each survivor | |

**Pruning rule.**
- θ = need − 1 when need ≥ 2, else need. Near rows are always computed, so the near toggle needs no re-run.
- For ticker t with m passes and r unevaluated conditions, **prune iff m + r < θ**.
- **Proof:** final met ≤ m + r < θ ≤ need, so t is not a match. When θ = need − 1, met < need − 1, so t is not near either. FAIL and NA never add. Functions are pure and keyed by (ticker, reference), so evaluation order cannot change a value. Displayed rows are fully evaluated.

**Effect by logic:**

| Logic | Pruning |
|---|---|
| ALL | at the second failure (first when need = 1) |
| AT LEAST k | when failures exceed n − θ |
| ANY | none; `meta.plan` says so |

**Counts and budget.**
- Each condition reports `evaluated`, `passed`, `na` and `exhaustive`. `options.exhaustive=true` disables pruning; FACT, exhaustive 3-condition screens take 0.35-0.56 s.
- The worst case is costed before running. Above `SCREENER_MAX_CPU_MS` the request is refused with `LIMIT_EXCEEDED {limit:'compute_budget', allowed, needed, costliest}`, never cut short.
- A cancel flag is checked between tickers.

**Verification:** a property test over random definitions (ALL, ANY, AT LEAST; 1-20 conditions mixing precomputed, dynamic and cross-sectional; many seeds). Pruned output must equal exhaustive output for the match set, near set, every displayed cell, `met` and `na_count`. A second test checks that stage order does not change the result.

**Permanent.**

## T8. Flow and bandarmology (Phase 9)

**Facts** (flow.md §1-5; verify_flow):
- F06 stores Regular-board foreign net for 1/5/10/20/40/60 sessions, % of value for 1/5/20, buy days, z-scores and percentiles (null until 252+N sessions), strength and acceleration. The latest cross-section reads in 23 ms.
- Broker-ranking metrics are stored nowhere.
- Multi-date F05 and F06 aggregates re-run at 3-8 s, with one timeout over 30 s.
- F02 on the latest date is sparse (ANTM −408 vs −477 B).
- F02 and F06 commit per ticker during a round of about 37 min.
- Rounds run per deployment with a token (C2 corrected).
- No bandar definition is approved (DESIGN.md:40,147).
- Board choice changes 20D foreign net for 168 of 841 stocks; 20 flip sign.
- Price volume equals Regular-board volume.

**Decision (PROPOSED), Phase 2: two xsection files in the same publication.**
- `flow_f06`:
  - the latest complete date's stored F06 columns per board;
  - 130-session one-day series per ticker and board: `foreign_net_1d`, `foreign_buy_1d + domestic_buy_1d`, trade count = `foreign_buy_freq_1d + domestic_buy_freq_1d` (FACT, equals trades).
- `broker_window`: raw F05 rows `d,b,i,m,bv,sv,bl,sl` for the last 41 sessions in the existing broker encoding, decoded by `datafile.brokerRows`.
  - Size INFERENCE: about 1.0 M rows (24,860 rows a date, live) and 8-12 MB gzip.
  - 41 = D ≤ 20 plus `within` ≤ 20 plus 1.
- **Read per date with literal bounds.** FACT: a CTE calendar join planned a seq scan taking 18.6 s (flow.md §5 Q2).
- **Completeness from the data** (reliability design): a date d is included only if the F06 Regular row count at d equals the number of tickers with F05 Regular rows at d. This avoids mid-round partial F06 and the stale RUNNING-row trap (verify_flow). No grant on `Monitoring_Stockbit_Update` is needed.

**In the worker:**
- Stored windows are read directly.
- Custom fnet and fpct windows, signed streak and trade spike `trades_t / mean(prior n)` are computed from the series on ticker sessions, the F06 calendar.
- Broker metrics use `flow.ts` `flowData`, `brokerNet`, `rollingSum` and `top5Accumulation` on the ticker's price bars, the Backtest calendar.
- `topNAccumulation` lives in screener core, with a test that N=5 equals `top5Accumulation` bitwise.
- **Self-check on every load:** recomputed 5/10/20/40/60-day sums and 1/5/20-day ratios must equal stored F06 where the ticker has the sessions. FACT: they match on 847 and 833 of 865 rows; the differences are short histories. A mismatch marks flow `DATA_INTEGRITY` and makes flow cells NA.

**Mapping of the prototype's flow metrics:**

| Prototype | Source / status |
|---|---|
| `fnet` | F06 stored or series; D + `within` ≤ 130 |
| `fpct` | F06 stored 1/5/20; others from the series |
| `fstreak` | series |
| `freq` | series |
| `broker` | F05 window; any of the 112 `IDX_Broker_Profile` codes; D ≤ 20 |
| `topacc` | `topNAccumulation` |
| `adv` | price `liquidity()`, never broker-lagged |
| `mfi`, `cmf`, `obv` | registry I47, I45, I40 |
| `silent` | technical transform |
| `bandar`, `bavg`, D-day breadth | after definitions are approved (P9); shipped disabled with a reason until then |

When approved:
- `bavg` uses the gross VWAP Σbuy_value / (Σbuy_lots·100) of the top-3 net buyers. FACT: this equals Stockbit Avg Buy.
- Breadth = buyers / (buyers + sellers). FACT: F03's ratio is not equivalent (verify_flow B5).

**Own flow screener, built on governed columns** (flow.md §4):
- F1-F3, F4 streak, F5 unusual (z-score and percentile, disclosed as null when history is short), F6 acceleration, F7 strength, F8 cross-sectional percentile;
- B1 top-N, B4 single broker;
- D1 trade spike, D4 participation.

C1 institutional vs retail is deferred (current-state classes, not point-in-time). Thresholds are per-condition parameters, never the prototype's global `BANDAR` object.

**Board.** Regular by default, with an all-boards variant summed from one-day values. Every flow reference carries `board` (P8). Send to Backtest is lossless only for all-board `fnet`, `broker` and `top5`.

**Freshness.**
- `flow_through` is the last complete date; every flow cell carries its `eval_date`.
- `FLOW_LAGGED` applies when the lag exceeds the user maximum, default 1 session (P10).
- INFERENCE: the 19:00 WIB run can start before a round finishes (round 11:08-12:58 UTC vs run 12:05 UTC). Flow then catches up at the next publication.

**Grants.** A forward migration creates `terminal_publisher_feature_reader` (NOLOGIN), with SELECT on `Feature_06_Foreign_Domestic` (optionally `Feature_04_Technical_Indicator` for the parity file), granted to `terminal_publisher_login` only. It updates the `provision_terminal_logins.py` reach set and ends with a `$verify$` block.

**Rejected:**
- A SQL Feature_07 table (reliability's Phase 3): a second top-N formula and inline stockbit-updater coupling. Revisit through onboarding if the AI needs these metrics.
- A DB read in the worker (simplicity design).
- Per-request F05 or F06 aggregates.
- F02 latest rows (sparse).

**Cost:** INFERENCE, about 10-40 s of DB time per publication in per-date index reads. `EXPLAIN (ANALYZE, BUFFERS)` evidence is recorded with the first run.

**Verification:**
- Self-check.
- `topN(5)` ≡ `top5Accumulation`.
- All-board `fnet`/`broker` ≡ Backtest `flowCondition` on published broker files for sample tickers.
- A completeness-gate fixture (partial date excluded).
- A lag fixture.

**Permanent;** bandar items wait for approval.

## T9. Fundamentals and universe filters (Phase 10)

**Ships in Phase 1** (FACT, data exists):

| Filter | Source and rule |
|---|---|
| Security type | stock |
| Sector and industry, include and exclude | `IDX_Stock_Universe` via the `ref` file. Values and counts come from data: 12 sectors, 58 industries + `Undefined`. Never `Universe_Equity_Description`, which is swapped on 844 of 844 rows (ERRORS D23). |
| Price ≥ | last close |
| 1D | snapshot |
| ADV20 ≥ | `liquidity()`; median ratio 1.0001 to exact Regular value |
| Traded on E | stale and suspension proxy, labelled as such; default on (P4) |
| Corporate-action break | flag from `ref`: PBSA 1:2 split, FORU rights (D22; RSI 22.8, SMA50 706 vs close 302); default exclude (P4) |
| History length ≥ N bars | censored at 2018-01-02 |

**Phase 2, after validation:** dividend yield TTM by ex-date and years with dividends.
- Source: `idx_event_annotation`, 5,301 events for 628 tickers.
- Labelled: amounts are not split-adjusted and include special dividends.
- Validated against an independent sample first.

**Shown disabled with a reason, never a silent no-op:**
- market cap and its buckets and column (EXEC-MCAP is waiting for "go");
- index membership, listing board, special notation and FCA (**the prototype's default `exclNotation:true` becomes off**), free float;
- the 28 statement metrics, Piotroski, Altman, Magic;
- NIM, NPL, CAR, CASA and LDR: `applies_to: Industry=Banks` (48 banks), `NOT_APPLICABLE` elsewhere.

The 8 fundamental presets and the fundamental legs of the 3 combined presets are disabled with reasons (P11).

**Availability** is derived at run time from the registry and from the xsection files present: `AVAILABLE`, `REQUIRES_DATA`, `REQUIRES_DECISION` or `NOT_APPLICABLE`. It is never enumerated in UI code.

**Point-in-time requirements** for future data: availability or filing date, vintages, period type, currency, split basis aligned with price (A2.7). Fundamental values are "today only" and are never used historically.

**Disclose:** the five F06-only tickers outside the universe (AKKU, CRAB, GTBO, TRUE, UNSP; verify_flow).

## T10. Screen Performance History (Phase 15)

**Decision (PROPOSED): defer the Portfolio123-style feature (P14).** The prototype's view is relabelled for what it is: "Stock vs IHSG", rebased 1M/3M/6M/1Y. FACT: it has no rebalance and no historical universe (html_ui.md §3.9). It is served by `/preview` from snapshot bars aligned with `asOf`.

**Why defer.** FACT:
- the price table holds 0 delisted tickers (survivorship);
- sector history starts on 2026-09-28; there is no index, board or notation history;
- prices are back-adjusted before 2026-09-12 and raw after (D22), so past level filters look ahead;
- broker classes are current-state;
- there are no fundamentals.

**Rejected:**
- A labelled non-point-in-time technical evaluator now: survivorship makes every curve look better.
- The Backtest engine: 12-ticker cap, and the worker must not change.

**Path to un-defer:** a point-in-time universe including delisted tickers, an adjusted-price fix in the data layer (D22/K4), then either `evaluate.ts` at past `at` (no new engine) or a Backtest screen-universe release.

**TEMPORARY deferral.**

## T11. Saved screens, My metrics, watchlist (Phase 16)

**Facts:** no server storage exists (edge_conventions.md §3.1); `edge_bff` per-owner tables are the precedent; the prototype uses `localStorage edge-*`.

**Decision (PROPOSED; P12).** One forward migration, in house style:
- `BEGIN`, `lock_timeout`, a `$preflight$` block, COMMENTs, `REVOKE ALL FROM PUBLIC`, exact grants to `edge_bff_runtime`, a `$verify$` block checking each privilege one call at a time and nothing extra, and the rollback as a comment.

**Tables:**
- `edge_bff.screener_items`:
  - `item_id` (`^scr_[0-9a-f]{32}$`), `owner_key`, `kind` (`screen` or `metric`), `name` (1-120 characters, trimmed);
  - `definition` jsonb, an object of at most 64 KiB;
  - `schema_version`, `registry_version`, `screener_registry_version`, `definition_hash`;
  - `revision` (409 on a stale write), `created_at`, `updated_at`;
  - `UNIQUE(owner_key, kind, name)`, index `(owner_key, kind, updated_at DESC)`.
- `edge_bff.watchlist_items(owner_key, ticker ^[A-Z0-9]{1,12}$, added_at, PK(owner_key, ticker))`, with SELECT, INSERT and DELETE only.

**Companion changes:** `scripts/provision_edge_bff_login.py`, `tests/conftest.py`, migration refusal tests, README Persistence, DATABASE_CHANGELOG with live read-back.

**Rules:**
- Definitions are validated on write through the worker's `/v1/validate`.
- They are re-validated on load. A parameter that became invalid shows "needs review" with the field; it is never adjusted silently.
- Limits `SCREEN_LIMIT` and `WATCHLIST_LIMIT` (422), following the `PIN_LIMIT` precedent.
- `localStorage scr.*` holds only conveniences: theme, panel sizes, last open screen.

**If the migration is not approved at the gate:** a TEMPORARY local adapter (`scr.screens`, `scr.metrics`, `scr.watchlist`, same `screen/v1` JSON) with a one-time import into the tables later.

**Permanent** (server path).

## T12. Send to Backtest (Phase 14)

**Decision (PROPOSED).** One portable definition, the same object used for run, save and CSV metadata. `to-backtest.ts` is a pure translation with an explicit classification:

| Lossless | Lossy (to `left_out`, with a reason) |
|---|---|
| Registry indicator conditions `gt`, `lt`, `crosses_above`, `crosses_below` with lhs price or output and rhs output or value of the same instance; parameters valid by the narrow-only rule; sent as `RegCard` | `between` |
| Supertrend or PSAR direction | cross-instance comparisons other than core SMA `macross` |
| Core patterns `breakout` up, `volspike`, SMA `macross`, `macd` divergence, crosses and histogram | transforms |
| Donchian prior band ≡ `breakout` | per-condition `within` unless every event shares one N ≤ 20 **and** there is no state or value condition (FACT: `window_bars` applies to states too, `conditions.ts:269-292`; no silent semantic change) |
| All-board `fnet`, `broker`, `top5` (Rp B → IDR via `DISPLAY`) | Regular-board flow; top-N with N ≠ 5; ratios, VWAP, streak, frequency |
| ADV ↔ `min_avg_value_20d_idr` | other universe filters and fundamentals ("screen only") |
| | more than 12 tickers (P13) |

FACT: the prototype's `toBacktest` maps none of the 53 (html_model.md §2.4); it is replaced, not ported.

**Handoff.**
- The screener frame writes a one-shot `sessionStorage['edge-backtest-import']`: `{v:1, source:'screener', definition_hash, price_data_version, evaluation_date, mode, ticker|tickers, entry:{logic, at_least, window_bars, cards}, left_out}`.
- It posts `{type:'edge-nav', route:'backtest'}`.
- The shell accepts the message only when `event.origin === location.origin` and `event.source` is its frame. No data travels in the message or the URL.
- Precedent: `edge-side-attach` and its Chromium test.

**Backtest change: page only.**
- `app.ts boot()` reads and deletes the key once, after `applyCatalog()` and before `load()`.
- A new `src/import.ts` converts via `legacyCard`, registry defaults, `withinLimit` and core validation, and shows a toast naming what was left out. It shows a "different data version" note when the handoff's `price_data_version` differs.
- **Untouched:** `backtest/src/core/*`, `apps/backtest-worker/**`, `backtest-registry.json`.
- **Prerequisites:** read `BACKTEST_END_TO_END.md` and `CONTRACT.md` in full and update both (CONTRACT §10). Land with or after BACKTEST-LOAD, which edits the same `boot()` (`PLAN.md:930-934`; M248).

**Verification:**
- Losslessness property test: for every lossless kind, the screener's `evaluate(...)[at]` equals the Backtest `conditionSeries(calc, toBacktest(c))[at]` at every bar on fixtures.
- Round trip: definition → cards → wire → validation passes.
- Lossy-list tests: `between`, mixed `within`, Regular flow.
- The 12-ticker rule.
- A Chromium test: frame → shell → Backtest frame.

**Permanent.** The lossy list shrinks when the Backtest adopts more operators in its own release.

## T13. API contract (Phase 11)

**edge-bff routes** under `/api/v1/screener/` (PROPOSED), following `app/backtest.py` conventions:
- session cookie; `Depends(write)` (Origin + CSRF) on every POST, PUT and DELETE;
- `loads()` refusing NaN, Infinity, 1e400 and lone surrogates;
- body ≤ 128 KiB;
- `error_of` + `public_data` redaction;
- `guard()` answering `SCREENER_DISABLED` / `SCREENER_NOT_READY`;
- relay on the event loop, read timeout = worker deadline + 10 s, `unless_gone` cancellation;
- latest wins per owner with `client_order {page, seq}` (409 `SCREEN_REPLACED`).

| Route | Purpose |
|---|---|
| `GET catalog` | ETag = `data_version` + `screener_registry_version`, checked every 60 s. Not a 60 s TTL rebuild, which is the BACKTEST-LOAD class of problem. Holds: versions; data status (`price_through`, `flow_through`, `broker_behind_sessions`, `published_at`, refresh state); limits; registry subset with ranges, shapes, tests, `history_class`, `cost_class`; flow, fundamental and universe items with availability and reason; groupings with counts; presets with availability and match/near counts at `data_version` |
| `GET universe` | per-ticker attributes, about 845 rows, about 20 KB gzip (INFERENCE); ETag = `data_version`. Popover counts update locally through the shared `universe.ts`; the server re-applies the same function. |
| `POST run` | one screen |
| `POST preview` | `{definition, ticker, data_version}` → last 260 OHLCV bars, the IHSG closes aligned with `asOf`, overlay tails, markers (event bars per condition), the ticker's cells and status even outside the universe. 409 `DATA_VERSION_CHANGED` when the version moved. |
| `POST validate` | used by save and by Send to Backtest |
| `POST counts` | at most 50 saved definitions, cached per (`data_version`, `definition_hash`) |
| `GET/PUT/DELETE items[/{id}]` | saved screens and metrics |
| `GET/PUT/DELETE watchlist[/{ticker}]` | watchlist |

**Run request:**
```
{schema_version:1, client_order:{page,seq},
 definition:{universe:{security_types:['stock'], sectors_in, sectors_out, industries_in, industries_out,
   price_min, adv20_min_idr, min_history_bars, traded_on_eval_date, exclude_price_breaks, tickers, metric_filters},
  conditions:[{id:'^[0-9a-z]{1,6}$', enabled, label?, test}], logic:'all'|'any'|'at_least', at_least},
 options:{exhaustive:false, explain:false}}
```

**Run response** (rows, gzip):
```
{schema_version:1,
 versions:{screener_engine, registry, screener_registry, price_data, flow_data|null, definition_hash},
 data:{evaluation_date, price_through, flow_through|null, broker_behind_sessions|null, published_at},
 universe:{listed, eligible, stale_excluded, filtered_out},
 conditions:[{id, source:'precomputed'|'dynamic'|'flow'|'xsection', metric, params_resolved, is_default, kind, unit,
   evaluated, passed, na, exhaustive, eval_date_basis}],
 need, match_count, near_count,
 rows:[{ticker, name, sector, industry, board:null, market_cap:null, last, chg_1d_pct, adv20_idr, last_bar_date, stale,
   flags, status:'match'|'near', met, need, na_count,
   cells:[{id, status:'pass'|'fail'|'na'|'not_evaluated', value, lhs, rhs, unit, eval_date, event_date, bars_ago,
   market_sessions_ago, last_event_date, reason}]}],
 warnings, timings_ms, plan?}
```

- Rows are matches ∪ near.
- With no active conditions, the response lists the universe (`mode:'universe_only'`).
- Values are raw doubles to 12 significant digits.
- Sorting, paging, search and CSV happen on the client: one response is one snapshot, and paging never re-runs.

**Errors:**

| Status | Codes |
|---|---|
| 422 | `INVALID_INPUT`, `INVALID_CONDITION{field}`, `UNKNOWN_INDICATOR`, `PARAM_OUT_OF_RANGE{field,min,max}`, `METRIC_UNAVAILABLE{metric,availability,reason}`, `LIMIT_EXCEEDED{limit,allowed,needed}` |
| 424 | `DATA_UNAVAILABLE`, `DATA_INTEGRITY` |
| 409 | `BUSY`, `SCREEN_REPLACED`, `DATA_VERSION_CHANGED`, `REVISION_CONFLICT` |
| 503 | `SCREENER_DISABLED`, `SCREENER_NOT_READY` (Retry-After), `SCREENER_UNAVAILABLE` |
| 504 | `TIMEOUT` |

Every refusal names the field and the fix, and the limits are published in the catalog first (the AGENTS gate rule: a rule visible before writing, how to pass it, examples, and a message that names the fix).

**Initial limits** (PROPOSED, provisional, replaced by Phase 17; P5):
- 20 active conditions, 8 universe metric filters;
- `within` ≤ 130 for technical, flow maxima derived from the window;
- lengths ≤ derived caps;
- compute budget from the cost model;
- worker deadline 20 s;
- one screen in flight per owner, worker queue 4;
- response INFERENCE ≤ 2 MB JSON (FACT: 845 × 5 values = 112 KB / 37 KB gzip).

**Worker private API:** header `x-screener-worker-key` (≥ 32 characters) on every route except `/health`. Routes: `GET /health` (versions, snapshot age, refresh state), `/v1/catalog`, `/v1/universe`, `/v1/run`, `/v1/preview`, `/v1/validate`, `/v1/counts`.

## T14. Frontend integration (Phases 12-13)

**Decision (PROPOSED).** A Vite + TypeScript sub-app, `apps/edge-bff/screener/`:
- `base:'/screener-app/'`, one IIFE classic script at the end of `<body>`, `cssCodeSplit:false`. FACT: the CSP forbids inline scripts (`main.py:39-48`).
- Framed at `/screener` like Backtest and Terminal.
- `SCREENER_CSP` with `connect-src 'self'` only: the page fetches nothing from the bucket.

**A 1:1 port of the prototype layout** (P6 covers the visible catalogue changes), using the EDGE theme key `edge-auth-monitor-theme`. A thin client: no formula code in the bundle; it imports only `contract.ts` and `universe.ts`.

**What changes from the prototype:**
- synthetic data, `XI`, `MEMO` and the legacy helpers are removed;
- a `fixture` build exists only for visual tests, with a bundle test proving fixture code is absent from production (the Backtest precedent);
- `XPARAM` is replaced by the catalog (typed booleans, real min/max, `not_accepted` hidden);
- one near rule;
- unavailable items disabled with reasons;
- consistent "Clear all" and liquidity clears;
- pagination no longer resets on unrelated edits;
- accessibility: `aria-sort`, keyboard rows, dialog focus return, `aria-live` toast;
- ticker search inside the page; the shell keeps ⌘K;
- `lightweight-charts` 5.2.1 from npm instead of the 197 KB inline copy.

**Preview (Phase 13).**
- `POST /preview`, then candles, overlays and markers drawn with the `CandlestickSeries` + `createSeriesMarkers` pattern of `backtest/src/signals.ts`.
- The "why it passed" list shows the server cells.
- "Stock vs IHSG" comes from the same answer.
- "Open in Terminal" sets `localStorage 'ml.symbol'` (FACT, `main.ts:117`).
- Rejected: the `/bundle` plus in-browser recompute (C2).

**Other behaviour:**
- Condition edits are debounced 350 ms with latest-wins.
- Sort, page, search, near toggle and CSV are client-side over at most about 845 rows.
- CSV holds the visible rows in the current sort with a metadata header (screen name, `evaluation_date`, `price_data_version`, `registry_version`, `definition_hash`) and per-cell value, status, event date and bars ago.
- Preset counts come from the catalog, not from 26 screens at boot.

**Shell touch points** (edge_conventions.md §1.7, §2.4):
- `static/index.html`: nav, `ScreenerPage` frame, `go()`, `App`, and the postMessage navigation listener;
- `edge-labels.js` `screener:{nav, frameTitle}`;
- `main.py`: routes, assets, CSP;
- Dockerfile stage and `.dockerignore`;
- tests for the tab list `['Monitor','Terminal','Backtest','Screener']` and the image COPY list.

## T15. Security, limits, observability, Railway topology (Phase 19)

**Security** (PROPOSED, FACT patterns):
- The browser never receives DB URLs, bucket credentials, `TERMINAL_PROXY_KEY`, `SCREENER_WORKER_KEY` or internal hosts.
- The xsection routes are absent from the browser allow-list.
- The worker holds no DB or bucket credentials.
- edge-bff accepts only a private host for the worker (the `config.py:75-98` pattern).
- Presigned URLs and keys are never logged (the `terminal.ts` rule).
- Every store statement filters `owner_key`, every write uses `Depends(write)`, and names render as text.

**Topology (PROPOSED; dev only; no deploy without "go"; deploy outside 00:00-01:00 and 12:00-13:05 UTC, M250; claim only at the exact deployment's SUCCESS):**

| Service | Change | Deploy |
|---|---|---|
| `screener-worker` (new) | 1 replica, `sfo`, private `http://screener-worker.railway.internal:8080`, restart ALWAYS, healthcheck `/health`, `/ready` only with a loaded snapshot. Variables: `SCREENER_WORKER_KEY`, `TERMINAL_URL`, `TERMINAL_PROXY_KEY=${{terminal-api.TERMINAL_PROXY_KEY}}`, `SCREENER_THREADS`, `SCREENER_CACHE_BYTES`, `SCREENER_CACHE_DIR`, `SCREENER_MAX_CPU_MS`, `SCREENER_CAP_BUDGET_MS`, `SCREENER_DEADLINE_MS`, `SCREENER_MAX_CONDITIONS`, `SCREENER_QUEUE`, with no defaults for limits (backtest-worker convention). Memory starts at 2 GB, then is set to the measured peak × 1.5. | GitHub `main` |
| terminal-publisher | xsection writer | CLI |
| terminal-api | `/state` and `/xsection` | CLI |
| edge-bff | routes, `SCREENER_WORKER_URL`/`SCREENER_WORKER_KEY` pair, sub-app | GitHub `main` |
| backtest-worker, feature-04-worker, stockbit-updater, feature-01-worker | **none** | — |

Update `.railway/railway.ts` and RAILWAY_CHANGELOG, then run `railway config pull --force` and `railway config plan`.

**Observability:** JSON logs with no secrets.
- **refresh:** `{data_version, published_at, files, bytes, grant_ms, download_ms, decode_ms, defaults_ms, integrity_failures, snapshot_digest, rss}`.
- **run:** `{definition_hash, data_version, n_conditions, stages:[{name, in, out, ms}], conditions:[{id, source, cache, tickers_evaluated, cpu_ms}], pruned, queue_ms, total_ms, payload_bytes, status}`.
- `options.explain` returns the plan; the catalog shows the refresh state; `/health` reports snapshot age.

## T16. Files, database, Feature 04, backfill, tests, benchmark, phases, risks

**Create** (PROPOSED):
- `apps/screener-worker/`:
  - `Dockerfile` (repository-root context; COPY its `src`, `apps/edge-bff/{terminal/src/calc, terminal/src/data/indRegistry.json, backtest/src/core, screener/src/core}`, `apps/backtest-worker/{src/terminal.ts, loader}`);
  - `package.json` (no dependency), `README.md`, `CONTRACT.md`;
  - `src/{server, config, refresh, snapshot, pool, thread, run, preview, catalog, version, errors, log}.ts`;
  - `tests/`.
- `apps/edge-bff/screener/`:
  - `package.json`, `vite.config.ts`, `index.html`;
  - `src/` (UI modules, `api/{types,live,fixture}.ts`);
  - `src/core/*` (the T6 list, `screener-overlay.json`, generated `screener-registry.json`, `presets.json`);
  - `scripts/build-screener-registry.mjs`;
  - `tests/`.
- `apps/edge-bff/app/screener.py`, `apps/edge-bff/tests/test_screener.py`.
- `scripts/screener/{check_backtest_untouched.mjs, parity_f04.py, bench.mts}`.
- `verification/screener/{F04_PARITY.md, BENCHMARK.md, E2E.md}`.

**Change:**
- `apps/terminal-publisher/publisher.py` + tests (xsection writer, index in `state.json`, pruning of unreferenced xsection objects).
- `apps/terminal-api/app/{main.py, bucket.py}` + tests (`/state` shared with BACKTEST-LOAD, `/xsection`).
- `apps/edge-bff/app/{main.py, config.py}`, `static/{index.html, edge-labels.js}`, `Dockerfile`, `.dockerignore`, `README.md`, pinned tests.
- Phase 1b: `apps/edge-bff/backtest/src/{app.ts, import.ts}` + page tests, `BACKTEST_END_TO_END.md`, `CONTRACT.md`.
- `.railway/railway.ts`, `PROJECT_CONTEXT.md`, PLAN/EXEC (approval words), ERRORS, RAILWAY_CHANGELOG, DATABASE_CHANGELOG.

**Must not change** (tripwire): `indicators.ts`, `indRegistry.json`, `backtest-registry.json`, `apps/edge-bff/backtest/src/core/**`, `apps/backtest-worker/**`, `features/feature04/**`, `apps/feature-04-worker/**`, the Feature 04 tables, `apps/stockbit-updater/**`.

**Database changes** (each needs "go"):
1. **Phase 1:** `edge_bff.screener_items` and `edge_bff.watchlist_items` (T11).
2. **Phase 2:** `terminal_publisher_feature_reader` group with SELECT on F06 (optionally F04), granted to `terminal_publisher_login` only, with `$verify$`, plus the `provision_terminal_logins.py` reach update.

No public table, so no Table_Catalog, Column_Catalog or Feature_Catalog rows and no index. The publisher's new statements use existing indexes (Price seq scan; F05 `trade_date_idx`; F06 `(trade_date, market_board)` with literal bounds), and their `EXPLAIN (ANALYZE, BUFFERS)` is recorded with the first run.

**Feature 04 changes:** none. **Backfill:** none; the first publication builds the files from existing data.

**ERRORS entries to record** (Phase 0):
- Donchian same-bar `price > upper` never fires;
- the I37 label contradicts `F`;
- I09 factor 0 accepted;
- `annualization_periods` floored silently;
- the stale RUNNING `Monitoring_Stockbit_Update` row and the "date not JSON serializable" failure;
- the planned refill → about 840 `REPAIR_REQUIRED` and the IHSG abort in `backfill.py` and `bootstrap_states.py`.

`AI_TOOLS.md`, `AI_MODELS.md` and the system prompt are unaffected.

**Test plan** (run by hand; FACT: there is no CI):
1. **Formula parity:** existing `terminal/tests/calc` stays green; snapshot vs Feature 04 (T3); snapshot vs Feature 01 for I35, I37, I17; `F` on typed views ≡ arrays.
2. **Precomputed vs dynamic:** bit-identical, same key (T4).
3. **Condition parity:** the T6 list.
4. **Data dates:** E = `price_through`; stale tickers; `event_date`/`bars_ago` across 09-17/18; `flow_through` < `price_through` → `FLOW_LAGGED`; refresh integrity fixture.
5. **Universe:** sector from `ref` only (swapped-UED fixture); ADV ≡ `liquidity()`; price, traded and break flags; `Undefined`; IHSG excluded.
6. **Match logic:** ALL, ANY, AT LEAST, n = 1, at_least > n, one near rule across run, preview and CSV, plus the planner property test.
7. **Flow:** self-check, completeness gate, `topN(5)`, all-board parity.
8. **Send to Backtest:** T12.
9. **Isolation tripwire;** backtest-worker `npm test`, Backtest vitest, smoke and visual 1:1; Feature 04 pytest (49).
10. **Contract drift:** T5 1-7.
11. **E2E:** Chromium with fixture worker and fixture terminal-api (page → edge-bff → worker → render → preview → CSV → save → Send to Backtest → import), then real-data E2E on dev after "go", recorded in `verification/screener/E2E.md`.

**Benchmark plan (Phase 17)** on the dev worker with real rack data:
- **Scenarios:** default-only (1/5/10 conditions); one custom (RSI 7); five custom (O(N) and O(N·n)); mixed; event (MACD cross within 5); flow (Phase 2); the whole universe with no conditions; worst case allowed; warm vs cold tail cache; result-cache hit; refresh cold vs disk-cached; concurrency 1/2/4/8 during and outside a refresh and during a Backtest job.
- **Measure:** p50/p95 at the worker and through edge-bff; CPU ms; peak RSS; bytes and files from terminal-display per refresh; publisher run delta and DB buffers (`pg_stat_io` deltas); cache hit ratio; payload raw and gzip; preview latency.
- **Outputs:** K, queue depth, memory limit, `SCREENER_MAX_CPU_MS`, cap budget, `within` and condition limits.

**Phases:**

| Phase | Contents | Prerequisite |
|---|---|---|
| 0 | contract (overlay + generator), screener core, unit, property and parity tests on local data; ERRORS entries; decisions | none (branch push already permitted) |
| 1 (dev) | publisher xsection price + ref, terminal-api `/state` + `/xsection`, screener-worker, edge-bff relay and page (technical + universe + presets + preview + CSV + saved screens per P12), then the Phase 17 benchmark | "go" on P1, P3 and the migration |
| 1b | Send to Backtest page import | with or after BACKTEST-LOAD |
| 2 | flow files + grant migration, flow metrics and presets, dividends after validation, optional Feature 04 reconciliation file | "go" |
| 3 | bandar, `bavg`, breadth after definitions; Ichimoku via a registry release | P6, P9 |
| 4 | market cap (EXEC-MCAP), fundamentals source, performance history once point-in-time data exists | separate approvals |

**Risks:**
1. Price breaks (D22: PBSA, FORU) give false technical signals everywhere. The screener flags and excludes by default; the fix is in the data layer.
2. Freshness is about 3 h behind the database each trading evening by design. If the user wants fresher data, the rack schedule changes for everyone (P1).
3. Publisher and terminal-api CLI deploys and coordination with BACKTEST-LOAD (`/state`, `boot()`) and the M250 PR (M248 history).
4. Flow lag recurs without a token (C2); a partial 19:00 run delays flow by one publication.
5. Unmeasured memory, threads and sin → sfo download time; the SharedArrayBuffer path depends on the bit-parity gate.
6. Long O(N·n) lengths and ANY logic (no pruning) need calibrated caps and budget.
7. No CI: tripwires work only if run before each merge.
8. The shipped screener looks smaller than the prototype: 11 of 26 presets, market cap and the notation default are disabled with reasons.
9. The refill → `REPAIR_REQUIRED` hazard weakens Feature 04 as an oracle until repaired; the screener runtime is unaffected.
10. Version skew between page and worker deploys is limited to the wire schema, because the page holds no formula code; M252 skipped merges remain.
