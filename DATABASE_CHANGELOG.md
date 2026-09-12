# Database changelog

## 2026-09-13 — Create Feature Catalog for validated Feature 01

- Target: `public."Feature_Catalog"` in Railway project `lucid-patience`, environment `dev`, PostgreSQL service `bb21a9f4-a9d3-4a51-945f-fa86b63f4b86`.
- Added forward-only migration `database/migrations/20260913_001_create_feature_catalog.sql` without changing `Feature_01_Stock_Daily`, raw tables, application services, or schedules.
- Live inspection found one of the four locked Feature tables: `Feature_01_Stock_Daily` with 29 physical columns. Feature 02–04 and any prior Feature Catalog were absent.
- Created all 18 required metadata/governance columns using the existing mixed-case table/lowercase-column convention, with primary key `(feature_table, feature_column, version)`, controlled Feature table/category/version checks, mandatory nonblank metadata, timezone-aware timestamps, and automatic `updated_at` maintenance.
- Added a governance trigger that rejects an active catalog entry unless its exact target table and column physically exist in schema `public`.
- Registered exactly 29 active `v1` definitions for Feature 01 and zero premature entries for Feature 02–04. Each entry records grain, category, detailed meaning and formula, exact source references, trading-observation lookback, minimum history, unit, null rule, refresh trigger, and dependency rule.
- Coverage validation PASS: 1 Feature table found, 29 physical Feature columns, 29 catalog entries, 29 active entries, zero missing definitions, zero catalog targets pointing to missing columns, zero duplicate definitions, and zero mandatory-field violations.
- Source validation PASS: zero broken source-table or source-column references. All references use the actual live PostgreSQL table and column casing.
- Formula spot-check PASS against `refresh_feature_01_stock_daily(date, text[])` for `return_20d_pct`, `volatility_20d_ann_pct`, and `volume_zscore_20d`. Formula checks belonging to Feature 02–04 are not applicable until those tables exist and pass their own validation.
- Governance test PASS inside a rolled-back savepoint: an attempted active definition for nonexistent column `does_not_exist` was rejected.
- Overall status: PASS. Feature Catalog is ready as the semantic/metadata layer for Feature 01; future Feature tables must be validated before their catalog rows are appended.

## 2026-09-12 — Create and backfill Feature 01 stock daily

- Target: `public."Feature_01_Stock_Daily"` in Railway project `lucid-patience`, environment `dev`, PostgreSQL service `bb21a9f4-a9d3-4a51-945f-fa86b63f4b86`.
- Added forward-only migration `database/migrations/20260912_001_create_feature_01_stock_daily.sql`.
- Created the ticker/trading-date feature table with primary key `(ticker, date)`, a separate `date` index, source close/volume and current Sector/Industry, trading-observation lags, percent returns, annualized 5/20/60-observation volatility, volatility changes, 20-observation volume metrics, rolling highs, and drawdowns.
- Added `public.refresh_feature_01_stock_daily(date, text[])`. A null date performs the initial full refresh; an incremental call recomputes the changed row and up to 120 following trading observations for the selected ticker set. Empty ticker arrays are safe no-ops, zero denominators return null, and an advisory transaction lock serializes refreshes.
- Initial SQL-side backfill completed in approximately 54 seconds and inserted 1,303,728 rows across 844 tickers from 2018-01-02 through 2026-09-11. The latest date contains the same 829 rows as the price source. The resulting table and indexes use approximately 379 MB.
- Reconciliation PASS: exact source/feature row and ticker counts, zero duplicate keys, zero missing or extra keys, zero close/volume/Sector/Industry mismatches, zero negative source values, zero one-day returns below -100%, zero positive drawdowns, and zero incomplete classifications.
- Window validation PASS: all 1/5/20/60 lag boundaries, complete-window volume/high fields, complete-window volatility fields, and zero-denominator volatility-change rules matched their expected null behavior.

| Calculated field | NULL count | NULL rate |
|---|---:|---:|
| `close_1d_ago` | 844 | 0.0647% |
| `close_5d_ago` | 4,220 | 0.3237% |
| `close_20d_ago` | 16,880 | 1.2947% |
| `close_60d_ago` | 50,555 | 3.8777% |
| `return_1d_pct` | 844 | 0.0647% |
| `return_5d_pct` | 4,220 | 0.3237% |
| `return_20d_pct` | 16,880 | 1.2947% |
| `return_60d_pct` | 50,555 | 3.8777% |
| `abs_return_1d_pct` | 844 | 0.0647% |
| `volatility_5d_ann_pct` | 4,220 | 0.3237% |
| `volatility_20d_ann_pct` | 16,880 | 1.2947% |
| `volatility_60d_ann_pct` | 50,555 | 3.8777% |
| `volatility_5d_change_pct` | 67,235 | 5.1571% |
| `volatility_20d_change_pct` | 74,665 | 5.7270% |
| `volatility_60d_change_pct` | 130,642 | 10.0206% |
| `volume_avg_20d` | 16,036 | 1.2300% |
| `volume_std_20d` | 16,036 | 1.2300% |
| `volume_ratio_20d` | 16,036 | 1.2300% |
| `volume_zscore_20d` | 16,039 | 1.2302% |
| `high_20d` | 16,036 | 1.2300% |
| `high_60d` | 49,717 | 3.8134% |
| `drawdown_20d_pct` | 16,036 | 1.2300% |
| `drawdown_60d_pct` | 49,717 | 3.8134% |

- Independent formula validation PASS for BBCA on 2026-09-11, SUPA at its 121st observation on 2026-07-01, and zero-volume DSSA on 2020-10-14. All stored values matched separate calculations within floating-point tolerance.

| Sample | Source inputs | Independently expected | Stored | Difference | Result |
|---|---|---:|---:|---:|---|
| BBCA 2026-09-11 `return_1d_pct` | close 6,325; previous trading-observation close 6,425 | -1.5564202334630295 | -1.5564202334630295 | 0 | PASS |
| BBCA 2026-09-11 `volatility_20d_ann_pct` | 20 complete close-derived daily returns | 19.06043383091717 | 19.06043383091717 | 0 | PASS |
| SUPA 2026-07-01 `return_1d_pct` | close 515; previous trading-observation close 535 | -3.738317757009346 | -3.738317757009346 | 0 | PASS |
| DSSA 2020-10-14 `volume_ratio_20d` | volume 0; complete 20-observation average 377,500 | 0 | 0 | 0 | PASS |

- Incremental validation PASS inside a rolled-back test transaction: BBCA historical refresh affected exactly 121 rows, latest-date refresh affected one row, repeated runs preserved the full ticker checksum, and each historical refresh completed in approximately 0.28 seconds.
- Query-plan validation used the `(ticker, date)` primary key for a 60-row BBCA history query (0.091 ms) and the `date` index for an 829-row latest-market query (2.363 ms).
- The first migration attempt referenced a renamed CTE alias and failed before backfill; PostgreSQL rolled back the entire transaction. The alias was corrected, absence of partial objects was verified, and the migration then applied successfully.
- Raw price and universe tables, all other Feature tables, Railway services, schedules, and price-cron application code were intentionally left unchanged. Automatic price-cron integration remains a separate future step.

## 2026-09-12 — Correct IDX stock-universe Sector and Industry values

- Target: `public."IDX_Stock_Universe"` in Railway project `lucid-patience`, environment `dev`, PostgreSQL service `bb21a9f4-a9d3-4a51-945f-fa86b63f4b86`.
- Corrected all 844 reference rows in one short transaction by swapping the values stored in `Sector` and `Industry`; table structure, the `Ticker` primary key, and every other column remained unchanged.
- Pre-change validation found 59 granular classifications under `Sector` and 12 broad classifications under `Industry`, confirming that the values were reversed semantically. Neither column contained null or blank values.
- A one-row `AADI` test changed `Coal` / `Energy` to `Energy` / `Coal` inside a transaction, then rolled back and verified the original row before the full correction ran.
- Post-change verification found 12 broad `Sector` values and 59 granular `Industry` values, zero null or blank values, and all 844 ticker pairs matching the approved swapped interpretation. Example: `AADI` now has `Sector = Energy` and `Industry = Coal`.
- Content checksum changed from `00549007e7ef4fd027dce108a965ce35` to `f1a77bc69c2ae71c8237a91690cdfe8a`; total row count remained 844.
- `public."Universe_Equity_Description"`, all other tables, and all Railway services were intentionally left unchanged. The pre-existing PostgreSQL TCP proxy was reused and left untouched. No CSV was created.
- Refreshed `DATABASE_SCHEMA.md` and `Database_Table_Status` from the verified live database after the correction.

## 2026-09-09 — Add Telegram command audit and deduplication ledger

- Added forward-only migration `database/migrations/20260909_002_create_telegram_command_log.sql`.
- Created `public."Telegram_Command_Log"` to audit authorized inbound bot commands separately from completed price results and outbound notification delivery.
- Enforced unique `telegram_update_id` values so a Telegram webhook retry cannot start a second Railway execution.
- Added per-service request-time and status indexes used by the rapid-click cooldown and operational review.
- Applied the migration to Railway PostgreSQL and regenerated `DATABASE_SCHEMA.md` plus `Database_Table_Status`.
- End-to-end verification recorded one accepted RECOVERY trigger and rejected an identical replay as a duplicate. The resulting RECOVERY execution `9926d137-6316-4c04-a1c2-099d87bd4735` completed with `NEEDS_REVIEW`, and its outbound notification was recorded as `SENT`.

## 2026-09-09 — Add Telegram notification delivery ledger

- Added forward-only migration `database/migrations/20260909_001_create_telegram_notification_log.sql`.
- Created `public."Telegram_Notification_Log"` to record `SENDING`, `SENT`, and `FAILED` delivery state without changing `Monitoring_Price_ALL.id` or `Monitoring_Price_ALL.execution_id`.
- Enforced one completed notification per `(source_table, source_execution_id, notification_type)` so repeated wake requests cannot send the same execution twice.
- Recorded Telegram message IDs, attempt count, sent time, and last delivery error for audit and retry handling.
- Applied the migration to Railway PostgreSQL and verified an end-to-end test: the first request was `SENT`; the second request for the same execution was treated as a duplicate and reused the same log row.

This file records database structure changes and material data loads. Times are Asia/Jakarta unless stated otherwise.

## 2026-09-07

### Broker-summary authentication-stop repair and recovery

- Target: `public."IDX_Broker_Summary"` and `stockbit_broker_summary_load_log`.
- Incident: after the prior Stockbit credential expired, both historical workers continued handling the authentication-limit exception as an ordinary date failure.
- Impact: 24 dates in each historical range, 48 total, were incorrectly marked `NEEDS_REVIEW`; previously completed data remained unchanged.
- Repair: authentication-limit exceptions now bypass date retries and `NEEDS_REVIEW` writes, reach the process-level `STOPPED_INVALID_TOKEN` handler, and return exit code 3 to stop the supervisor.
- Verification: an automated regression test simulated the fifth HTTP 401, confirmed `STOPPED_INVALID_TOKEN`, and confirmed that `record_needs_review` was not called.
- Recovery: restarted both historical supervisors with a refreshed in-memory credential; no secret value was stored in files or Git.
- First verified recovered dates: 2022-08-24 loaded 22,229 rows in the recent range, and 2019-09-10 loaded 14,124 rows in the older range. Both workers continued with no authentication error or new `NEEDS_REVIEW` date.

### Manual current-day IDX price run

- Target: `public."Price_Stock_Indonesia_IDX"` for 2026-09-07.
- Railway execution: `f4fd425d-edfe-433a-9925-99d052c794c5` (`MANUAL`, `DAILY`).
- Queried all 844 live `IDX_Stock_Universe` tickers; accepted and upserted 824 exact-date candles.
- Left 20 symbols missing because TradingView returned no candle dated 2026-09-07; no prior candle was substituted.
- Resulting price table: 1,300,396 rows, 844 distinct tickers, date range 2018-01-02 through 2026-09-07.
- Verification: 824 distinct target-date tickers, all 20 monitoring missing tickers absent for the target date, zero weekend rows for 2026-09-05/06, and zero duplicate `(ticker, date)` keys.

### Price-run monitoring history

- Target: `public."Monitoring_Price_ALL"`.
- Added `execution_id`, `trigger_source`, and `query_time` so every manual or scheduled execution remains separate history.
- Replaced the old date/run-type unique key with unique `(execution_id, exchange, asset_type, timeframe)`.
- Existing monitoring rows were retained and backfilled as scheduled legacy executions.
- Migration: `database/migrations/20260907_002_track_manual_price_runs.sql`.
- Verification: all three columns are non-null, the trigger-source check accepts only `SCHEDULED`/`MANUAL`, and the new execution key is active.

### IDX stock-universe classification schema

- Target: `public."IDX_Stock_Universe"`.
- Recorded the removal of obsolete profile columns and the final `Sector`/`Industry` mapping from `Universe_Equity_Description` in an idempotent migration.
- Migration: `database/migrations/20260907_001_simplify_idx_stock_universe.sql`.
- Verification: 844 rows, 844 distinct tickers, complete non-null `Sector` and `Industry`, and no remaining obsolete columns.

### Historical broker-summary range split

- Target: `public."IDX_Broker_Summary"`.
- Existing historical worker range changed to 2025-08-31 backward through 2021-01-01.
- Added a concurrent older historical worker covering 2020-12-31 backward through 2018-01-01.
- Both historical workers are database-only and do not produce local CSV files.
- Concurrency: three API workers per process, six combined, after twelve combined workers triggered a temporary Stockbit HTTP 429 response.
- Resume safety: dates already marked `COMPLETED` remain preserved and are skipped; the two active ranges do not overlap.
- First post-split verification: the recent worker loaded 21,527 rows for 2023-12-14; the older worker completed 2020-12-31 and continued to 2020-12-30. Both had zero `NEEDS_REVIEW` dates.

## 2026-09-06

### Rename daily-price table

- Action: rename `public."price_stock_indonesia_IDX"` to `public."Price_Stock_Indonesia_IDX"`.
- Data impact: no rows changed.
- Migration: `database/migrations/20260906_001_rename_price_stock_indonesia_idx.sql`.
- Verification: exact table name, row count, date range, constraints, and indexes read back from PostgreSQL.

### Initial daily-price load

- Target at load time: `public."price_stock_indonesia_IDX"` (renamed afterward).
- Source: `indonesia_stocks_daily_from_2023.csv`.
- Source SHA-256: `588064313348629bdb8f6a53c35fc5aeff4e7483f78ff36f8ca6101eaf5b2bc7`.
- Rows: 668,967.
- Distinct tickers: 844.
- Trading-date range: 2023-01-02 through 2026-09-04.
- Query date: 2026-09-06.
- Verification: zero null rows, zero duplicate `(ticker, date)` keys, and all 844 tickers matched `IDX_Stock_Universe`.

### Historical daily-price load (2018-2022)

- Target: `public."Price_Stock_Indonesia_IDX"`.
- Source: `indonesia_stocks_daily_2018_2019.csv`.
- Source SHA-256: `3b92ba28daae47469b2022dcf2cf497df6dadcfba7f3a7b5d7357d61f245d121`.
- Source rows: 209,816; 547 distinct tickers; trading-date range 2018-01-02 through 2019-12-30.
- Source: `indonesia_stocks_daily_2020_2022.csv`.
- Source SHA-256: `4a57e019dc364320e506dba30dbdb35365030ed100ba88de04fe3f897bf1e4d3`.
- Source rows: 420,789; 694 distinct tickers; trading-date range 2020-01-02 through 2022-12-30.
- Combined load: 630,605 new rows and 695 distinct tickers; no existing `(ticker, date)` keys were overwritten.
- Result: the target increased from 668,967 to 1,299,572 rows and now covers 2018-01-02 through 2026-09-04.
- Verification: exact source-to-database row match, zero duplicate source keys, zero post-upsert mismatches, valid nonnegative OHLCV values, and all source tickers matched `IDX_Stock_Universe`.

### Broker-summary backfill recovery

- Target: `public."IDX_Broker_Summary"`.
- Cause: the previous Stockbit session credential expired and affected dates were marked `NEEDS_REVIEW` instead of stopping the whole backfill.
- Recovery: restarted the local supervisor with a refreshed credential; completed dates were skipped automatically.
- First verified recovered date: 2026-03-17.
- Rows loaded for the first recovered date: 24,501.
- Verification: the load status advanced to 2026-03-18 with no authentication error; the remaining date range continues in the background.

### Price automation monitoring table

- Action: created `public."Monitoring_Price_ALL"`.
- Migration: `database/migrations/20260906_002_create_monitoring_price_all.sql`.
- Purpose: track `DAILY` and `RECOVERY` price runs by exchange, universe `Security Type`, timeframe, and target date.
- Expected-symbol source: distinct `IDX_Stock_Universe."Ticker"` values grouped by `Exchange` and `Security Type`.
- Missing-symbol handling: stores both a count and JSON ticker list; unrecovered symbols finish as `NEEDS_REVIEW`.
- Duplicate protection: unique `(exchange, asset_type, timeframe, update_for_date, run_type)` monitoring key.
- Initial rows: 0; no TradingView production query was run during table creation.
- Verification: 18 columns, primary key, run key, status/count/time checks, and date/status index read back from live PostgreSQL.

### Historical broker-summary backfill started

- Target: `public."IDX_Broker_Summary"`.
- Source: Stockbit broker-activity API; no source file or local CSV is produced.
- Requested range and order: 2025-08-31 backward through 2018-01-01; weekends are skipped.
- First verified trading date: 2025-08-29 because 2025-08-31 is a Sunday.
- First verified load: 28,715 rows from 672 complete broker/investor/board filters, with zero duplicate natural keys.
- Parallelism: runs alongside the existing ascending backfill using separate process status and log files.
- Authentication safety: five consecutive HTTP 401/403 responses stop the query as `STOPPED_INVALID_TOKEN` without advancing through the remaining dates.
- Status: the continuous historical backfill remains active; per-date results are recorded in `stockbit_broker_summary_load_log`.
