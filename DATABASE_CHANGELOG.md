# Database changelog

This file records database structure changes and material data loads. Times are Asia/Jakarta unless stated otherwise.

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
