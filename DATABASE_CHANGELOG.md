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

### Broker-summary backfill recovery

- Target: `public."IDX_Broker_Summary"`.
- Cause: the previous Stockbit session credential expired and affected dates were marked `NEEDS_REVIEW` instead of stopping the whole backfill.
- Recovery: restarted the local supervisor with a refreshed credential; completed dates were skipped automatically.
- First verified recovered date: 2026-03-17.
- Rows loaded for the first recovered date: 24,501.
- Verification: the load status advanced to 2026-03-18 with no authentication error; the remaining date range continues in the background.
