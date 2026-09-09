# Database changelog

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
