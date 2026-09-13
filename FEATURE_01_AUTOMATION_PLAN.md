# Feature 01 price-ingestion automation plan

Automatic price-driven Feature 01 calculation is active in Railway `dev`. A PostgreSQL price-row trigger enqueues work, and the always-on `feature-01-worker` service processes it. Local retry and historical tests and a live Railway worker test passed. `Feature_01_Stock_Daily` and `refresh_feature_01_stock_daily(date, text[])` remain the calculation targets.

## The three control tables

| Table | Grain and key | Responsibility |
|---|---|---|
| `Feature_Calculation_Queue` | One row per `(feature_table, ticker, price_date)` | Durable work item for a specific source-candle insertion/correction; stores source `ingestion_time`, queue state, claim/retry metadata, and last error. |
| `Feature_Status` | One row per `(feature_table, ticker)` | Current per-ticker summary: latest source version/change, last successful calculation, outstanding work count, current status, and last error. It is a read model, not the work queue. |
| `Feature_Calculation_Log` | One row per completed attempt, keyed by identity `id`; unique `(feature_table, ticker, price_date, attempt_no)` | Immutable worker-attempt outcome, including failed retries and claims superseded by newer source data. |

The queue state is `PENDING` → `PROCESSING` → `DONE` or `FAILED`. `DONE` means the **Feature calculation** succeeded; it does not merely mean price ingestion finished. Retryable `FAILED` work can return to `PENDING`.

`Feature_Status.status` is `PENDING`, `PROCESSING`, `SUCCESS`, or `FAILED`. `SUCCESS` replaces the earlier illustrative `UP_TO_DATE` label. It is valid only when all committed source changes for that ticker have been processed and validated, with no outstanding queue work. A new price upsert changes the summary back to `PENDING` even if its trading date is historical. No status row is required for a ticker with no source candle.

## Implemented fields

`Feature_Calculation_Queue`: `feature_table`, `ticker`, `price_date`, `source_ingestion_time`, `source_execution_id` (nullable), `status`, lifetime `attempt_count`, per-source-version `source_attempt_count`, `next_attempt_at`, `claimed_at`, `claim_token`, `claim_expires_at`, `last_error`, `created_at`, `updated_at`, and `completed_at`.

`Feature_Status`: `feature_table`, `ticker`, `latest_price_date`, `latest_source_ingestion_time`, `last_successful_source_ingestion_time`, `last_successful_price_date`, `last_calculated_at`, `pending_count`, `processing_count`, `failed_count`, `status`, `last_error`, and `updated_at`.

`Feature_Calculation_Log`: `id`, `feature_table`, `ticker`, `price_date`, `source_ingestion_time`, `attempt_no`, `result` (`SUCCESS`, `FAILED`, `SUPERSEDED`), `started_at`, `finished_at`, `rows_refreshed` (nullable), and `detail` (nullable). The log retains attempt history when a queue key is reopened for a later source version.

`Feature_Status` counts/status are reconciled from queue transitions; it never independently declares success while a newer source version is pending. Its `latest_price_date` records the latest trading date observed by the enqueue flow. Queue keys have a foreign key to source candles; log rows have a foreign key to queue keys. The queue has partial ready/recovery indexes and a ticker/state index. The trigger only enqueues rows with non-null `ingestion_time`; the existing price cron supplies this timestamp. `source_execution_id` is currently null because the database trigger does not receive the price execution ID.

## Active transaction and worker behavior

1. The price writer upserts a valid `Price_Stock_Indonesia_IDX` candle. Its PostgreSQL trigger inserts/reopens the Feature 01 queue item to `PENDING` **in the same database transaction**. The source version is `ingestion_time`. If the transaction rolls back, neither price nor queue change remains.
2. After commit, the worker atomically claims eligible `PENDING` work with `FOR UPDATE SKIP LOCKED`; the same worker reclaims expired `PROCESSING` leases and retries eligible `FAILED` work with backoff. It does not query TradingView.
3. The worker calls `refresh_feature_01_stock_daily(price_date, ARRAY[ticker])`. It must process each changed date needed for a ticker; one historical correction can affect its own feature row and up to 120 later trading observations. Several changes more than 120 observations apart cannot be collapsed into one date.
4. The worker validates the affected `(ticker, date)` coverage and records `DONE` only if its claim token and `source_ingestion_time` still match the queue row. A newer price upsert must not be overwritten by a stale worker completion.
5. `Feature_Status` becomes `SUCCESS` only after all queue items for that ticker are `DONE` for current source versions. Errors leave the queue `FAILED`, save a concise reason, and set the summary to `FAILED` unless other work is actively processing.
6. Worker calls are idempotent; the PostgreSQL refresh routine protects calculation overlap with an advisory transaction lock. The worker handles one queue item per claim, polls every five seconds, and permits five claims per source version with exponential retry delay. It uses a ten-minute claim lease and one always-on Railway replica.

The activation reconciliation found no missing Feature 01 keys or close/volume/Sector/Industry mismatches among 1,303,728 source/Feature pairs. Historical ticker summaries were not blindly marked `SUCCESS`; only committed price changes with non-null `ingestion_time` create queue/status rows. Old price rows with null `ingestion_time` remain covered by the Feature 01 backfill but do not have a known source version in this queue. A separate historical replay would be needed if per-ticker queue history for those rows is desired.

Feature 01 also copies current Sector and Industry from `IDX_Stock_Universe`. A universe-classification change must independently enqueue or invoke a refresh for the affected ticker, or `Feature_Status` must not claim comprehensive freshness. This dependency is separate from the price-ingestion trigger.

Deployment status: Railway service `feature-01-worker` (`de4e34ee-435b-408f-a77f-63e6698a2dab`) deployed Git commit `6c1ee21` as deployment `5465b07b-5919-4dc1-a513-871ba7ca4ad2`, status `SUCCESS`. The live worker log showed `worker_started`, then claimed and completed a metadata-only BBCA 2026-09-11 re-ingestion: queue `DONE`, ticker status `SUCCESS`, log `SUCCESS`, one Feature row refreshed. Rollback-only enqueue, a local `FAILED` → retry → `SUCCESS`, and a historical 121-observation refresh also passed. Sector/Industry changes remain a separate dependency.
