# Feature 04 audit (read-only), 2026-10-27

Scope: everything about Feature 04 that matters before a screener redesign. That covers the code, the migrations, the docs, live PostgreSQL through pgweb (role `pgweb`, read-only, 30 s timeout) and the query plans. I changed nothing in the repository: `git status` is clean. Every SQL statement and its output is saved under `/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/feature04/` (`qNN_*.sql` / `qNN_*.out`). DB time when I read it: 2026-10-27 19:34 UTC, PostgreSQL 18.6.

Note on the scratch folder: it also holds `q01_basics.txt` … `q20_triggers_funcs.txt` and `repo_copy/apps`. Those came from a concurrent run of the same area. Where they overlap with my numbers they agree (4.36 rows/page, 49 tests passed). Every number below comes from my own `.sql`/`.out` files.

## 1. Verdict

| Topic | Finding | Label |
|---|---|---|
| Health | 868/868 instruments DONE. 44,268/44,268 column statuses SUCCESS. 0 FAILED/BLOCKED. Checkpoints 6,076 = 868×7. Latest data 2026-10-27, finished 10:09 UTC for equity and 11:03 UTC for bonds. | FACT (q11, q12, q22) |
| History depth | Equity runs **2018-01-02 → 2026-10-27, about 8.8 years**, not 3. Median 1,802 rows per ticker; 384 tickers start on 2018-01-02. Bonds go back to 2016-01-01. | FACT (q04) |
| Coverage vs price | All 844 equity tickers match `Price_Stock_Indonesia_IDX` (Daily, final) exactly: same row count, first date and last date. The only price-only ticker is IHSG, which lives in `_INDEX`. Bonds match 24/24. | FACT (q05, q06) |
| Screener default path | "Latest row per ticker" takes 22 ms warm; "latest date" takes 2 ms warm and 84 ms cold. Windows of 90 days to 1 year across all tickers take 2.2–2.6 s cold. | FACT (q13, q14, q23) |
| Storage | The heap is 2,479 MB at **4.36 rows/page**. The same-schema `_INDEX` clone holds 19.88 rows/page. That is about 4× bloat: roughly 1.9 GB dead space. | FACT (density) / INFERENCE (bloat size) |
| Fit to the 53-indicator registry | At default parameters, F04 can serve 8 of 53 indicators (sma, macd, adx [adx output only], rsi, bollinger, plus %B, bandwidth and natr derived from them). It stores no custom parameters. It has no `ema` at the registry default of 20. | FACT (code: engine.py, backtest-registry.json, indicators.ts) |
| Option A "extend F04" | Possible, but heavy. Each indicator has to be implemented twice (full TA-Lib engine plus streaming checkpoint state). Changing VERSION invalidates every checkpoint. Two maintenance tools would currently abort at IHSG. The `_INDEX` table and the stockbit-updater image have to change in step. | FACT (code) / INFERENCE (abort) |

## 2. Code inventory and deployment

| File | Role | Evidence |
|---|---|---|
| `features/feature04/engine.py` (386 lines) | Pure full-history calculation (TA-Lib vector) plus diagnostics/availability validator. `VERSION='feature04-v3-smi14-5-5-th40-talib0.6.8-c0.6.4'` (l.21). 57 `COLUMNS` in physical order (l.51). 15 float indicators, 25 TA-Lib patterns (l.28-42), inside_bar, 9 SMI/swing fields, `close`. | FACT |
| `features/feature04/swing.py` | Literal replay of the Pine SMI 14/5/5 ±40 swing state (first-input EMA seed, l.21-22). | FACT |
| `features/feature04/incremental.py` (583 lines) | **Separate streaming re-implementation** of SMA/BB (TA-Lib add/output/subtract order), EMA, RSI, ATR, ADX, MACD signal and SMI/swing state. Candles use TA-Lib over a fixed 15-bar window. `STATE_VERSION='feature04-state-v3'` (l.36). | FACT |
| `features/feature04/pipeline.py` | Bounded manual refresh: 1–10 tickers, ≤366 days, ≤5,000 rows, dry-run by default (l.128-175). | FACT |
| `features/feature04/backfill.py` | Serial full-history writer: one ticker per transaction, COPY staging, hash-verified, resumable via `feature04_backfill_log`. **Equity only** (SOURCE/TARGET queries l.20-29). | FACT |
| `features/feature04/specs.py` | Per-column formula/usage text feeding the migration generators. Asserts the specs equal `COLUMNS` (l.99). | FACT |
| `apps/feature-04-worker/worker.py` (832 lines) | Always-on queue consumer, plus a Telegram outbox dispatcher. | FACT |
| `apps/feature-04-worker/bootstrap_states.py` | Rebuilds checkpoints from full history, shadow-checks the suffix against the full engine, optional stored-drift check. | FACT |
| Dockerfile | `python:3.12-slim`, `pip install -r requirements.txt`. The image copies only engine/swing/incremental plus worker/bootstrap; backfill.py, pipeline.py and specs.py are not in it (Dockerfile l.1-9). | FACT |
| Railway IaC | `feature-04-worker`: 1 replica, restart ALWAYS, watchPatterns `/apps/feature-04-worker/**` and `/features/feature04/**`. So any push to main that touches the engine redeploys the worker (`.railway/railway.ts:162-169`). | FACT |
| Second deployed engine copy | `apps/stockbit-updater/deploy.sh:13` copies `features/feature04` into the stockbit-updater image (TA-Lib 0.6.8 in its requirements). `refresh.py:149-183` → `scripts/backfill_index_features.py:148-158` recalculates IHSG with `engine.calculate` and COPYs `engine.COLUMNS` into a temp table `LIKE Feature_04_Technical_Indicator_INDEX` (l.253). | FACT |

**TA-Lib pin and installation (FACT):**
- Pins: `requirements.txt` has numpy==2.3.5, TA-Lib==0.6.8, psycopg[binary]==3.2.13; `dependencies.lock` holds the full lock.
- Installation is a plain pip wheel. I downloaded the PyPI wheel `ta_lib-0.6.8-cp312-…manylinux_2_28_x86_64.whl`; it bundles `ta_lib.libs/libta-lib-…so.0.6.4`. No C build step is needed.
- At runtime, `library_contract()` (engine.py:83-97) refuses anything except Python 0.6.8 / C 0.6.4, compatibility 0 and unstable period 0.
- incremental.py calls it at import time (l.39-41). INFERENCE: if the pin drifts, the worker crash-loops on start instead of writing different numbers.

## 3. Calculation model

- **Full engine** (engine.py:154-302):
  - Groups rows by (asset_type, ticker, Daily) and sorts them by date.
  - Never fills missing dates. Windows count the ticker's own valid rows; migration `20261025_016` records this as `window_basis=ENTITY_SESSIONS`.
  - An invalid OHLC row, or missing volume for an ordinary stock, gets NULL features and restarts all histories (`_segments`, `_valid` l.128-151).
  - Bonds and universe indices may have NULL volume (l.134-137).
  - FACT.
- **Formulas, from code:**
  - SMA, EMA, RSI, ATR, ADX and BBANDS are TA-Lib with defaults.
  - MACD = ema_12 − ema_26 (SMA-seeded); the signal is a TA-Lib EMA9 over the MACD values from bar 26 onward. This is not TA-Lib MACD's internal fast reseeding (l.257-266).
  - Candles: one TA-Lib call per bar over a fixed window of max-lookback+1 = 15 bars, so values do not depend on older history (l.100-117, 287-300).
  - inside_bar uses strict Decimal comparisons (l.274-280).
  - SMI and swing come from swing.py.
  - FACT.
- **Version history:**
  - Engine: `feature04-v1-talib0.6.8-c0.6.4` (42 columns) → `-v2-` (+adx_14, ema_50, ema_200, inside_bar) → `-v3-smi14-5-5-th40-…` (+9 SMI/swing).
  - Later additions did **not** bump the engine VERSION: `asset_type` (20261011_006) and `close` (20261011_008).
  - Feature_Catalog numbering is separate: v1 (42 rows, inactive), v2 (46, inactive), **v4 active (57)**. There is no v3 catalog row set for the main table.
  - Live: every one of the 1,389,238 rows carries the v3 string. I counted per year because a single full-table GROUP BY hit the 30 s timeout (q08, q09).
  - FACT.
- **Dependency bundles** (engine.py:62-80): MACD (and ema_12/26 → MACD), Bollinger and all 9 SMI/swing columns are retried and withheld as units. FACT.
- **Availability validation:**
  - Every row is checked against warm-up, candle lookback and conditional swing state. An unexpected NULL counts as a failure; an expected NULL counts as SUCCESS.
  - Code: `validate_output_availability` (engine) and `validate_incremental_availability` (incremental.py:523-583).
  - FACT.

## 4. Queue, checkpoints and incremental suffix (live design)

1. **Enqueue.** Row triggers fire AFTER INSERT/UPDATE/DELETE on `Price_Stock_Indonesia_IDX` (`enqueue_feature04_equity_price_row`) and `Price_Fixed_Income` (`enqueue_feature04_bond_price_row`). They fire only for a material change to a final Daily row (20261012_003 l.280-312). They call `enqueue_feature04_group`, whose latest body is in 20261025_011 l.88-139. That function:
   - skips universe indices;
   - classifies the ticker through `feature04_asset_type()`, which raises unless the ticker is in exactly one universe (20261011_006 l.32-49);
   - deletes checkpoints on or after the dirty date;
   - upserts one queue row per (asset_type, ticker, Daily), keeping `least(dirty_from_date)` while work is pending (or the new date if the row was DONE), bumping `requested_generation` and `work_revision`, and resetting attempts.

   FACT; live trigger list in q17.
2. **Claim.** `FOR UPDATE SKIP LOCKED LIMIT 1` with a 15-minute lease, at most 5 source attempts, backoff 30 s × 2^n capped at 30 min, polling every 5 s. The worker is a single replica and processes jobs serially (worker.py:37-41, 91-204, 816-828). FACT.
3. **Suffix.** The worker needs a checkpoint at exactly the last final source date before `dirty_from_date`, with matching `state_version`, `calculation_version` and source-chain SHA. It reads at most `correction_lookback_sessions` rows (IDX = 5, `Equity_Market_Schedule`) and keeps 5+2 = 7 checkpoints (worker.py:239-334). If any of this fails, the job ends **`REPAIR_REQUIRED` (terminal; no automatic full-history fallback)**. FACT.
4. **Write.**
   - Before the write, the worker re-checks the claim token, generation and revision; a stale job is logged SUPERSEDED (worker.py:571-582).
   - It deletes target rows for source dates that disappeared (worker.py:374-383).
   - It upserts only the successful columns, with `IS DISTINCT FROM`, so `calculated_at` is kept when nothing changed (l.386-413).
   - It replaces checkpoints, marks the queue DONE and the per-column status SUCCESS, and records `latest_value_available`/`null_reason`.
   - Failed groups → status FAILED plus retry; on exhaustion, terminal FAILED.
   - FACT.
5. **Monitoring and notification.**
   - The price cron opens `Monitoring_Feature04` in the price transaction (`apps/idx-price-cron/price_update.py:634-673`); a trigger on `Monitoring_Fixed_Income` does the same for bonds.
   - `finalize_runs` sets SUCCESS/PARTIAL/FAILED once every ticker is terminal.
   - The outbox waits until the price Telegram message is recorded sent (or the retry acknowledgement is recorded), then POSTs to telegram-monitor (worker.py:432-473, 735-813).
   - FACT.
6. **Retry.** telegram-trigger `/feature04` calls `request_feature04_retry` (SECURITY DEFINER), which accepts failures only. Since 20261012_004, the dirty date is always the oldest of the latest 5 final sessions (`feature04_retry_dirty_date`). Column retries expand to the dependency bundle. FACT.

**Source-correction behaviour:**
- FACT: a correction inside the last 5 sessions is recalculated exactly.
- INFERENCE from the code path: a correction older than 5 sessions, a first price for a brand-new ticker, or re-ingested history (for example after a split) makes the enqueue delete every newer checkpoint. The job then fails `REPAIR_REQUIRED`, and a Telegram retry cannot recover it, because it also needs the checkpoint immediately before the 5-session boundary, which was deleted.
- FACT: live log id 10264 shows exactly this case, `equity/IHSG REPAIR_REQUIRED … before 2018-01-02` on 2026-10-23 (q21).
- The repair is manual: `backfill.py --tickers X --write`, then `bootstrap_states.py --ticker X`, then requeue.
- Prices are split-adjusted at fetch (`price_update.py:311`). Stored history is not re-adjusted after a later split (comment in `apps/market-python-sandbox/app/service.py:51-55`). FACT. INFERENCE: F04 indicators carry a level break across a split.
- FACT (q04): no equity ticker starts after 2026-07-10, so no new listing has gone through this path since incremental mode began on 2026-10-12.

## 5. Equity, bonds and INDEX

- **Identity and classification.** `asset_type` is in the PK `(ticker, trade_date, timeframe, asset_type)`. CHECK constraint `asset_type IN ('equity','bonds')`. Classification is data-driven: `IDX_Stock_Universe` → equity, `Universe_Fixed_income` → bonds. FACT.
- **Bond inputs.** Bonds read `Price_Fixed_Income` where `metric_type='price' AND "Timeframe"='1D' AND is_final`. Volume may be NULL. FACT.
- **Universe indices (IHSG).** Excluded from the stock table since 20261025_011:
  - `is_universe_index()`;
  - trigger `stock_feature_index_guard` on F04 rejects index rows.

  FACT (q17).
- **`Feature_04_Technical_Indicator_INDEX`:**
  - Created `LIKE … INCLUDING ALL` with `CHECK asset_type='index'` (20261024_010).
  - Live: IHSG, 2,127 rows, 2018-01-02 → 2026-10-27, v3, last `calculated_at` 2026-10-27 12:39 UTC. 0 IHSG price dates are missing (q18).
  - It is rebuilt by the stockbit-updater INDEX refresh, not by the worker (FACT, refresh.py).
  - **Doc drift (FACT):** the Table_Catalog `update_rule` still says "automatic daily routing is not enabled" (q16).

## 6. Tests

- `features/feature04/tests`: test_engine, test_extensions, test_swing, test_incremental (five-position correction parity against the full engine), test_diagnostics, test_pipeline. FACT.
- I ran them on a scratch copy with the pinned venv (TA-Lib 0.6.8 / C 0.6.4, numpy 2.3.5): **49 passed in 1.86 s** (`pytest_feature04.out`). FACT.
- `test_selected_date_repair.py` and `test_repair_job.py` (fixed-income repair) need a Postgres URL and the `websocket` package. They were not run. FACT.
- The only CI workflow is `.github/workflows/database-schema-docs.yml`. CI runs no pytest for Feature 04. FACT.
- Extra recorded parity evidence:
  - 868-instrument incremental/full shadow plus a live re-run with `changed_rows=0` (`verification/feature04/INCREMENTAL_FINALITY.md`);
  - Terminal TS port vs stored F04: 23 tickers, 1,619 tests passed (`apps/edge-bff/terminal/tests/calc/PARITY.md`).
  - FACT (docs).

## 7. Who consumes Feature 04 (from grep plus ACLs)

| Consumer | How | Evidence |
|---|---|---|
| AI | `AI_table_catalog` active (stock + `_INDEX`). `AI_column_catalog`: 49 allowed, 8 hidden (tracking_*, temp_*, *_bar, calculation_version, calculated_at). `AI_calculation_catalog`: 57 ACTIVE. Grants to `market_ai_sql_reader` and `market_ai_preview_owner`. orc preview (`app/tools/preview.py:49-52`), sandbox `PRICE_TABLES` (`service.py:51`), Governor login provisioning (`scripts/provision_market_sql_governor_login.py:29`), ai-data-coverage (`coverage_job.py:37,106`). | FACT (q16, q17, q19) |
| Telegram / price | telegram-trigger `/feature04` (`telegram_trigger.py:103-146`), telegram-monitor (`telegram_monitor.py:30,285-335`), idx-price-cron monitoring. | FACT |
| INDEX | stockbit-updater → `backfill_index_features.py`. | FACT |
| Terminal / Backtest / EDGE BFF | **No runtime read.** terminal-publisher reads Price and F05 (`publisher.py:56-94`); terminal-api reads F05 (`store.py:15`). Only the test tool `terminal/tests/calc/tools/fetch_live.py` reads F04. Role `terminal_market_reader` has **no SELECT on F04** (relacl, q17). | FACT |
| Docs vocabulary | `Feature_Vocabulary` has no F04 rows (F01/02/03/05/06 only). | FACT (q24) |

## 8. Live coverage (bounded queries)

| Asset | Tickers | Rows | First → last | Starts 2018-01-02 / earlier / later | Ends on 2026-10-27 / earlier | Rows per ticker (min / median / max) |
|---|---|---|---|---|---|---|
| equity | 844 | 1,328,595 | 2018-01-02 → 2026-10-27 | 384 / 0 / 460 | 828 / 16 | 74 / 1,802.5 / 2,125 |
| bonds | 24 | 60,643 | 2016-01-01 → 2026-10-27 | 0 / 21 / 3 | 11 / 13 (US bonds end 2026-10-26) | 1,012 / 2,635.5 / 2,761 |

**First year of equity history:**

| Year | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|
| Tickers | 497 | 50 | 45 | 48 | 55 | 76 | 40 | 26 | 7 |

- No listing-date column exists: UNKNOWN in the DB for whether the other 460 start at listing. INFERENCE: spot checks match the public IPO dates (GOTO 2022-04-11, BUKA 2021-08-06, AMMN 2023-07-07, BREN 2023-10-09).
- **Stale tickers (last date before 2026-10-27):** ADHI 08-21, PPGL 09-04, IPAC 09-10, INPS 09-16, PTPP 10-02, CSMI and XSPI 10-06, IGAR and TFCO 10-15, BIKE 10-19, BSWD and MPRO 10-20, TRUK 10-21, MASB 10-22, MSIN and TGKA 10-26. FACT.
- **Short histories:** 10 tickers have under 200 rows (ema_200 NULL); 95 have under 750. FACT.
- **Session gaps:** against the 2,125 observed equity dates, 242 tickers have no gap, 602 have gaps, 220 miss more than 5% of sessions, 9 miss more than 50%; 88,288 ticker-sessions are absent in total (q20). F04 rows exist only on days the ticker has a price row. FACT.
- **Rows by year (all v3, Daily):**

  | Year | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 YTD |
  |---|---|---|---|---|---|---|---|---|---|
  | Equity rows | 98,508 | 111,308 | 120,392 | 143,979 | 156,418 | 167,995 | 181,537 | 188,824 | 159,634 |

  FACT (q09).
- **NULLs on the latest date** (equity 828 rows and bonds 11 rows on 2026-10-27):
  - every indicator and candle column has 0 NULLs, except ema_200 (8) and last_swing_high (5);
  - temp_high/_bar (789) and temp_low/_bar (468) are NULL by design when not tracking;
  - bonds: only the conditional temp_* columns are NULL.

  `Column_Status.null_reason` agrees (`EXPECTED_FORMULA_NULL`: ema_200 10, last_swing_high 5, temp_*). FACT (q10, q11).
- **`calculated_at`:** the base load was 2026-10-11 05:55–06:25 UTC (equity) and 13:53–13:55 UTC (bonds). The newest is 2026-10-27 10:09:36 (equity) and 11:03:44 (bonds). FACT.
- **Daily freshness:** DAILY runs finish 2.8–7.4 minutes after the price run opens at about 10:00–10:04 UTC (one outlier of 23.2 minutes on 2026-10-22), covering 827–834 tickers. Over the last 7 days the average job takes 0.20 s, the maximum 32.9 s, and jobs read 1 source row. FACT (q12, q22).
- **Control tables:**
  - Queue: 868 DONE, generation lag 0.
  - State: 868×7, `feature04-state-v3`.
  - Log: 11,964 SUCCESS, 1 FAILED (IHSG).
  - Outbox: 128 SENT.
  - Retry_Request: 0 rows.
  - Monitoring_Feature04: 44 SUCCESS / 73 SKIPPED runs.
  - `feature04_backfill_log`: 1,689 COMPLETED rows over 3 runs, 845 tickers (v2 and v3).

  FACT (q11, q12).

## 9. Query plans and latency

Indexes: PK btree `(ticker, trade_date, timeframe, asset_type)` and `Feature_04_Technical_Indicator_trade_date_idx (trade_date)` (q01). Settings: shared_buffers 128 MB, work_mem 4 MB (q15b).

| Query (EXPLAIN ANALYZE, BUFFERS) | Plan | Time |
|---|---|---|
| `DISTINCT ON (ticker)` latest row, `trade_date >= latest-10`, 21 columns, equity | Bitmap on trade_date_idx, sort; 5,953 rows → 835 tickers (828 current + 7 stale) | **22.0 ms**, 1,019 hits, 1 read |
| `SELECT *` on the latest equity date (subquery max) | Backward index scan + bitmap; 828 rows | **1.97 ms** warm |
| Latest date with `rsi_14<30 AND close>sma_50` joined to price | 839 heap blocks, one row per page | **84.1 ms** cold (837 reads) |
| `max(trade_date)` | Index-only backward | 0.07 ms |
| BBCA, 3 years, `SELECT *` | PK index scan | 17.7 ms (63 reads) |
| All equity, 90 days, 5 columns | Bitmap on PK (876 searches) | **2,579 ms** (17,100 reads) |
| Per-ticker 1-year max/min close | Parallel bitmap on trade_date_idx | **2,243 ms** (24,321 reads); the same on Price takes 1,649 ms |
| Full-table GROUP BY | — | **> 30 s timeout** |

The Governor acceptance results were already recorded: F04 P1–P5 pass after the date index (`DATABASE_INDEX_ACCEPTANCE.md:268-286`). FACT.

**Storage:**
- Heap 2,479 MB, 317,373 pages, **4.36 rows/page**. The same-schema `_INDEX` table holds 19.88 rows/page.
- Sum of `avg_width` is 359 B per row.
- Since the stats began: `n_tup_upd` 9,356,027 against `n_tup_ins` 1,393,549, with only 36,280 HOT updates. Last autovacuum 2026-10-11 (q15b, q25).
- FACT.
- INFERENCE: the repeated full-table rewrites of 2026-10-11 (v2, v3, asset_type and close backfills) left about 4× bloat, about 1.9 GB reclaimable. This bloat makes multi-day all-ticker scans read about 4× more pages.
- Reclaiming it needs VACUUM FULL or pg_repack, which takes an exclusive lock and needs approval (PROPOSED).

## 10. What F04 can serve to a 53-indicator screener (from code)

Sources compared: registry defaults in `apps/edge-bff/backtest/src/core/backtest-registry.json` and `terminal/src/calc/indicators.ts:215-246` (DEFAULTS), plus `F` at l.463-469, against the F04 columns.

| Registry key (default) | F04 | Equivalence |
|---|---|---|
| sma(20, close) | `sma_20` (and `sma_50`) | TA-Lib SMA; PARITY I01 max diff 0 |
| ema(20) | **none**: only 12/26/50/200 | — |
| macd(12/26/9) | `macd`, `macd_signal`, `macd_histogram` | Same "F04 method"; PARITY I06 diff 0 |
| adx(14,14) | `adx_14` only; no plus_di/minus_di | PARITY I07 1.1e-15 |
| rsi(14) | `rsi_14` | TA-Lib (flat window → 0) |
| bollinger(20, 2, SMA) | `bb_upper_20`, `bb_middle_20`, `bb_lower_20` | Population stdev |
| bollinger_pctb, bollinger_width, natr(14) | Derivable in SQL: (close−lower)/(upper−lower); 100·(upper−lower)/basis; 100·atr_14/close | INFERENCE (formulas l.463-469) |
| atr(14) | `atr_14` | TA-Lib (no TR on bar 0); TS follows it after the user decision "Yang ada kita sesuaikan saja dengan feature 4" (EXEC.md ~l.7877) |
| The other 45 indicators; any custom parameters | — | Must be computed on the fly |

F04 also stores things the 53 do not have: 25 TA-Lib candles, inside_bar, SMI and swing state. `INDICATOR_ALIGNMENT.md:13` says "24 candlestick codes"; engine.py:28-42 has **25**. That doc is wrong (FACT).

## 11. Option A: what "extend Feature 04" requires (from code)

1. **engine.py**
   - Add the column to `INDICATORS`/`EXTENSIONS`, append it at the end of `COLUMNS` (physical order, l.48-51) and add it to `FEATURE_COLUMNS`.
   - Add it to `REQUIRED_AFTER` (l.54-59) and, for multi-output indicators, to `dependency_closure`.
   - Add a `run_group` in `calculate_with_diagnostics`.
   - Bump `VERSION`; that was the precedent for every formula column, while the direct columns close/asset_type did not bump it.
   - FACT.
2. **incremental.py**
   - Add a **streaming state** for the indicator: `new_state`, `_reset_segment` keys, an update function, a group in `calculate_incremental`, and a rule in `validate_incremental_availability`.
   - Bump `STATE_VERSION`.
   - FACT.
   - INFERENCE: this doubles the implementation per indicator, and stateful ones are non-trivial (PSAR, SuperTrend, KAMA, TSI, KVO, NVI/PVI, cumulative OBV/ADL/PVT).
   - Volume indicators must be NULL for bonds and IHSG, where volume is NULL.
3. **specs.py** (the assert at l.99), the migration generators `scripts/generate_feature04*_migration.py` (historical: they still reference the old table name in their guards), and `FEATURE04_COLUMN_DEFINITIONS.md` / `FEATURE04_TECHNICAL_INDICATOR.md`. FACT.
4. **Forward migration** (pattern from 20261011_002/003):
   - Guarded `ALTER TABLE … ADD COLUMN` plus CHECK constraints and COMMENT on **both** `Feature_04_Technical_Indicator` and `_INDEX`. Without the `_INDEX` columns, the INDEX refresh COPY of `engine.COLUMNS` into `LIKE _INDEX` fails (`backfill_index_features.py:157,253`; INFERENCE).
   - `CREATE OR REPLACE feature04_output_columns()` (20261011_008 l.217-231), used by retry.
   - Table_Catalog and Column_Catalog rows.
   - Feature_Catalog: deactivate v4 and insert v5 rows for every column (ERRORS "v2 active catalog cutover ordering").
   - Baseline `Feature04_Column_Status` rows derived from the target, not the queue (lesson from 20261011_009).
   - AI_column_catalog and AI_calculation_catalog rows if the column is exposed (onboarding plan).
   - `scripts/audit_feature_catalog_semantics.py` fails if a physical column lacks an active definition (l.35-82).
   - FACT.
5. **Operations**, in order:
   1. Pause the worker (README).
   2. Run the migration.
   3. Run a full rewrite with `backfill.py --all-source-tickers --write`.
   4. Run `bootstrap_states.py` (dry-run, then write).
   5. Run ANALYZE (M206).
   6. Redeploy the worker (automatic on main) **and** stockbit-updater (manual `deploy.sh`).
   7. Refresh the INDEX table.

   Reason for the order: a VERSION/STATE_VERSION change makes every existing checkpoint incompatible (incremental.py:116-117; worker SQL l.283), so without the bootstrap every next price change fails `REPAIR_REQUIRED` for all 868 instruments. FACT (code) / INFERENCE (outcome).
6. **Current blockers in the tools (INFERENCE from code, not executed):**
   - `backfill.py` builds its ticker list from every price ticker, which includes IHSG. Writing IHSG trips `stock_feature_index_guard`, and the tool stops at the first failure (l.146-172).
   - `bootstrap_states.py` includes IHSG as equity, and its stored-row check raises a "Shadow row-count mismatch" (l.100-118, 72-76).
   - Both tools predate M219.
   - `backfill.py` has no bond path (equity-only queries).
   - `backfill.py` and `pipeline.py` source queries lack the `is_final`/`timeframe='Daily'` filters the worker uses. This is harmless today: every price row is Daily and final (q05).
7. **Measured cost from earlier runs (FACT, docs):**
   - v2 full rewrite: 844 tickers / 1.318 M rows in 258 s (`RAILWAY_CHANGELOG.md:727`).
   - 868-instrument shadow: 311.7 s (`INCREMENTAL_FINALITY.md`).
   - INFERENCE: a rewrite of all 1.39 M rows creates about 1.39 M more dead tuples on an already 4× bloated heap.
8. **Alternatives (PROPOSED, not evaluated in depth here):**
   - Serve the 8 covered indicators and derived %B, bandwidth and NATR from F04 at default parameters, and compute everything else on the fly from price.
   - Or put any screener-only stored columns in a separate table/worker, so the F04 version and checkpoint contract and its AI exposure stay untouched.
   - Either way, reading F04 from EDGE needs a new grant to `terminal_market_reader`, or another read path (FACT: the grant is missing today).

## 12. Discrepancies and documentation drift (FACT)

- The `_INDEX` Table_Catalog update rule says "daily routing not enabled", but stockbit-updater refreshes the table and today's rows exist (q18).
- `INDICATOR_ALIGNMENT.md:13` says 24 candles; the engine has 25.
- The counts in `DATABASE_CATALOG.md:108` and `FEATURE04_TECHNICAL_INDICATOR.md` (844 / 1,318,633 and 24 / 60,409) are snapshots from 2026-10-11. Live: 1,328,595 / 60,643.
- Catalog version label v4 vs engine string v3.
- `reltuples` 1,383,577 vs live 1,389,238 (ANALYZE 2026-10-23); within tolerance.
