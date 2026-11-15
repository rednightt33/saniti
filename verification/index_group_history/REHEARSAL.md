# EXEC-INDEX-GROUP-HISTORY stage 1-2: local rehearsal (2026-11-15)

Nothing here ran on the dev database. Dev was only read (pgweb, read-only role) to build the copy.

## Setup
- PostgreSQL 16, a local cluster, database `igh` (and `igh_base`, the same before migration A).
- Definitions read from dev with `extract_ddl.py` (columns, generated and identity columns, checks, keys, indexes, the
  chosen triggers and their functions): `IDX_Stock_Universe`, `IDX_Stock_Universe_History`, `Reference_History_Capture_Log`,
  `Database_Table_Status`, `Universe_Fixed_income`, `Stock_List`, `Stock_List_Member_History`, the six `*_INDEX` tables,
  `Price_Stock_Indonesia_IDX`, `price_stock_idx_intraday`, `price_stock_idx_intraday_quality`, `Table_Catalog`,
  `Column_Catalog`; triggers `index_feature_identity_guard`, `idx_price_optional_volume_guard`, `reference_history_capture`,
  `database_table_status_change_tracker`; functions `is_universe_index`, `capture_stock_universe_history`,
  `remark_intraday_sessions`. Foreign keys to tables outside the copy were left out.
- Data read with `load_data.py`: the universe (908 rows) and its history (914 rows, 911 open) and capture log (5), 48
  fixed-income tickers, 66 Stockbit lists, the catalog rows of the INDEX, universe and list tables, IHSG and BBCA daily
  prices from 2026-09-15 (88 rows) and their 1h intraday bars (603), a few IHSG rows of Feature 01 and 06 INDEX.

## Results

| Check | Result |
|---|---|
| Migration A `20261115_001` (sha256 5aabff76...) | COMMIT, self-check passed: 77 entities (MARKET 1, INDEX 32, SECTOR 11, GROUP 33), every list resolved to its list_key |
| A a second time | refused: "Feature_Index_Entity exists" |
| Guard (`guard_test.sql`, each in a rolled-back transaction) | IHSG broker row: accepted; GSALIM Feature 06 on 2024-01-02: accepted; GSALIM Feature 01: refused (no price); LQ45 before migration B: refused (not a universe index); GSALIM on 2023-12-29: refused (before rows_from); BBCA: refused (not registered); after B, LQ45: accepted |
| Intraday quality (`remark_test.sql`, 1h, 2026-09-15..11-13) | before and after A: 44 sessions, digest ba9f6c85f6a8d0c3d51899ecd7b14ac5, identical; with a daily-only index candle on Sunday 2026-10-04: before A 45 sessions (the Sunday counted), after A 44 |
| Migration B `20261115_002` (sha256 e300a06e...) without A | refused: "migration 20261115_001 ... is not applied" |
| B after A | COMMIT: 44 universe indexes; history capture recorded 43 new versions (911 -> 954 open rows); symbols and URLs as checked on TradingView (BISNIS27 -> IDX:BISNIS_27, IGRADE -> IDX:I_GRADE, ...) |
| B a second time | refused: "a Feature_Index_Entity ticker is already an IDX_Stock_Universe row" |
| `apps/idx-price-cron` tests (stage 1 code) | 41 passed, 5 skipped (38 passed before; 3 new: new index not loaded, naming one refused, calendar from the intraday index only) |
