# Feature 01 price-ingestion automation plan

The three control tables now exist in Railway PostgreSQL, but the enqueue writer, worker, recovery path, and price-cron integration are **not yet implemented**. Therefore Feature 01 does **not** calculate automatically after a price ingest. `Feature_01_Stock_Daily` and `refresh_feature_01_stock_daily(date, text[])` already exist. Creating queue/status/log tables alone does not run the refresh routine.

## The three control tables

| Table | Grain and key | Responsibility |
|---|---|---|
| `Feature_Calculation_Queue` | One row per `(feature_table, ticker, price_date)` | Durable work item for a specific source-candle insertion/correction; stores source `ingestion_time`, queue state, claim/retry metadata, and last error. |
| `Feature_Status` | One row per `(feature_table, ticker)` | Current per-ticker summary: latest source version/change, last successful calculation, outstanding work count, current status, and last error. It is a read model, not the work queue. |
| `Feature_Calculation_Log` | One row per completed attempt, keyed by identity `id`; unique `(feature_table, ticker, price_date, attempt_no)` | Immutable worker-attempt outcome, including failed retries and claims superseded by newer source data. |

The queue state is `PENDING` → `PROCESSING` → `DONE` or `FAILED`. `DONE` means the **Feature calculation** succeeded; it does not merely mean price ingestion finished. Retryable `FAILED` work can return to `PENDING`.

`Feature_Status.status` is `PENDING`, `PROCESSING`, `SUCCESS`, or `FAILED`. `SUCCESS` replaces the earlier illustrative `UP_TO_DATE` label. It is valid only when all committed source changes for that ticker have been processed and validated, with no outstanding queue work. A new price upsert changes the summary back to `PENDING` even if its trading date is historical. No status row is required for a ticker with no source candle.

## Implemented fields

`Feature_Calculation_Queue`: `feature_table`, `ticker`, `price_date`, `source_ingestion_time`, `source_execution_id` (nullable), `status`, `attempt_count`, `next_attempt_at`, `claimed_at`, `claim_token`, `claim_expires_at`, `last_error`, `created_at`, `updated_at`, and `completed_at`.

`Feature_Status`: `feature_table`, `ticker`, `latest_price_date`, `latest_source_ingestion_time`, `last_successful_source_ingestion_time`, `last_successful_price_date`, `last_calculated_at`, `pending_count`, `processing_count`, `failed_count`, `status`, `last_error`, and `updated_at`.

`Feature_Calculation_Log`: `id`, `feature_table`, `ticker`, `price_date`, `source_ingestion_time`, `attempt_no`, `result` (`SUCCESS`, `FAILED`, `SUPERSEDED`), `started_at`, `finished_at`, `rows_refreshed` (nullable), and `detail` (nullable). The log retains attempt history when a queue key is reopened for a later source version.

`Feature_Status` counts/status must be maintained from queue transitions; it must never independently declare success while a newer source version is pending. Its `latest_price_date` records the latest trading date observed by the future enqueue flow. Queue keys have a foreign key to source candles; log rows have a foreign key to queue keys. The queue has partial ready/recovery indexes and a ticker/state index. These are storage and integrity contracts, not active automation.

## Required transaction and worker behavior

1. The price writer upserts a valid `Price_Stock_Indonesia_IDX` candle and inserts/reopens its Feature 01 queue item to `PENDING` **in the same database transaction**. The source version is the newly assigned `ingestion_time`. If the transaction rolls back, neither price nor queue change remains.
2. After commit, a worker atomically claims eligible `PENDING` work. A recovery worker also reclaims expired `PROCESSING` leases and retries eligible `FAILED` work with backoff. Neither needs another TradingView query.
3. The worker calls `refresh_feature_01_stock_daily(price_date, ARRAY[ticker])`. It must process each changed date needed for a ticker; one historical correction can affect its own feature row and up to 120 later trading observations. Several changes more than 120 observations apart cannot be collapsed into one date.
4. The worker validates the affected `(ticker, date)` coverage and records `DONE` only if its claim token and `source_ingestion_time` still match the queue row. A newer price upsert must not be overwritten by a stale worker completion.
5. `Feature_Status` becomes `SUCCESS` only after all queue items for that ticker are `DONE` for current source versions. Errors leave the queue `FAILED`, save a concise reason, and set the summary to `FAILED` unless other work is actively processing.
6. Worker calls are idempotent; the PostgreSQL refresh routine already protects calculation overlap with an advisory transaction lock. Add bounded batch size, retry limits, and observability tests before deployment.

At rollout, reconcile existing Feature 01 keys and values against the price source before initializing historical ticker summaries as `SUCCESS`; do not pretend that old price rows with null `ingestion_time` have a known source version. Queue only committed new/revised price observations from the activation point onward, or explicitly plan a separate historical replay.

Feature 01 also copies current Sector and Industry from `IDX_Stock_Universe`. A universe-classification change must independently enqueue or invoke a refresh for the affected ticker, or `Feature_Status` must not claim comprehensive freshness. This dependency is separate from the price-ingestion trigger.

Implementation status: migration and rollback-only constraint tests for all three tables are complete. All three are intentionally empty. Remaining order: transactional price enqueue → worker/recovery path and attempt logging → status reconciliation → end-to-end tests → deploy one price service at a time. Do not initialize ticker `SUCCESS` rows without reconciling source and Feature 01, including Sector/Industry freshness.
