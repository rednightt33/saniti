# Feature04 fixed-income execution

User approved extending the existing Feature04 formulas to fixed-income OHLC from
`Price_Fixed_Income`, including the `asset_type` identity, universe-based classification,
full historical backfill, failure-only retry, and Telegram tracking. No ticker list is
stored in code: `IDX_Stock_Universe` resolves `equity`, while `Universe_Fixed_income`
resolves `bonds`; no membership or membership in both universes fails closed.

Migration `20261011_006_extend_feature04_to_bonds.sql` passed a complete rollback rehearsal
and was then applied with SHA-256
`9a9e14e9ba18e6b706cd573c01ee8be5a1f24823e3b4012316a50f8e8a144c45`.
Migration `20261011_007_document_fixed_income_feature04.sql` likewise passed rehearsal and
was applied with SHA-256
`c6ea3a0073dad10af18984633dda6084d67c9b2361e7ac6d85ef2da4df826488`.
The primary key is now `(ticker,trade_date,timeframe,asset_type)` and the table has 56
columns. All pre-existing 1,318,633 rows were classified as equity without payload replay.

The deployed worker read fixed-income rows only where `metric_type='price'` and
`"Timeframe"='1D'`. Bootstrap execution `f04-bonds-bootstrap-20261011` completed 24/24
ticker jobs from each ticker's earliest row through 2026-10-09. It wrote 60,409 bond
rows, with zero failed/partial attempts and 1,200 successful column-status records.
Source-to-target comparison found zero missing or extra keys for both asset classes.
All-row checks found zero mismatch for strict inside bar, the MACD identities, Bollinger
middle versus SMA20, universe classification, and the integer `break_swing_high` domain.

The fixed-income daily (`0 10 * * *`) and recovery (`0 23 * * *`) services remain separate
from IDX price cron and were not modified. Relevant fixed-income price writes enqueue only
the affected classified bond ticker. A committed `Monitoring_Fixed_Income` row creates a
Feature04 run and durable `PRICE_FIXED_INCOME` event. Telegram records the fixed-income
price result first; that source-specific acknowledgement opens the completion gate, and
the Feature04 result follows only after every eligible ticker is terminal. Both triggers
passed rollback-only database tests. The bootstrap Feature04 notification reached `SENT`.

Commit `b7b447177e645688786d616915bf88ee683f85a6` deployed successfully as worker
`26a26a7c-e5fc-4e4d-bcb0-0c15c5c74353`, monitor
`752235bb-2dd3-46e6-b25c-f3a1ad1d6d8b`, and trigger
`050c74c0-6d98-4081-9117-b805ab7c79fc`. The relevant local suite passed 56 tests, and
the live semantic audit passed with 147 active/verified definitions and Feature04 56/56
physical coverage. Machine-readable counts are in `cross_asset_validation.json`.
The private execution sandbox was explicitly destroyed after validation; terminal state is
recorded in `bonds_execution_cleanup.json`.
