# Feature 01 calculation worker

This Railway service processes committed price changes recorded in `public."Feature_Calculation_Queue"`. It does not query TradingView or alter the price cron schedules. Its only required secret/reference is `DATABASE_URL=${{Postgres.DATABASE_URL}}` over Railway private networking.

## Runtime contract

- One always-on replica runs `python worker.py`; it polls every 5 seconds when idle.
- The PostgreSQL price trigger adds/reopens one `PENDING` queue row per inserted or updated candle whose `ingestion_time` is non-null. The trigger and price write commit or roll back together.
- The worker atomically claims one due item with `FOR UPDATE SKIP LOCKED` and, with it, every other due item of the same ticker (EXEC-UNIVERSE-BROKER L3, user go 2026-11-05), sets one unique claim token and ten-minute lease on them, and commits that short claim transaction. A second worker cannot claim the same rows.
- In a separate transaction, it locks those queue rows (each item fenced by its own token and source version; one that changed is logged `SUPERSEDED` and stays for the next claim). One current item calls `refresh_feature_01_stock_daily(price_date, ARRAY[ticker])`: its own row plus at most 120 subsequent trading observations, validated on those 121 rows. Several current items call `refresh_feature_01_stock_daily(NULL, ARRAY[ticker])` once: the whole ticker, validated on every row. The function reads the full history in both cases and a row depends only on the 120 rows before it, so the result equals the per-item runs (`test_worker_db.py`), and a ticker with 2,200 new rows is computed once instead of 2,200 times (ERRORS M350). It commits `DONE` for every item, `Feature_Status`, and one `SUCCESS` log record per item together (`rows_refreshed` on the first item only).
- Source re-ingestion reopens the same queue key to `PENDING`, clears a stale claim, and resets the per-source retry counter. The lifetime attempt number remains monotonic so the attempt log is append-only. Claim token and source timestamp fencing prevent an older worker from marking newer work `DONE`.
- A failed calculation rolls back Feature writes, records `FAILED`, and retries after exponential backoff (30, 60, 120, then 240 seconds), up to five claims per source version. After the fifth failure, `next_attempt_at` becomes infinity and the item needs investigation or a new source ingestion. Expired processing leases are logged and reclaimed; an exhausted lease is finalized as `FAILED`.
- `Feature_Status.SUCCESS` means all queued price-ingestion versions for that ticker have been validated. It is **price-driven freshness**, not a guarantee that a later `IDX_Stock_Universe` Sector/Industry change was recomputed. That dependency needs a separate refresh path.

The queue, status, and log are operational data, not Feature formula definitions. The 29 Feature 01 formulas remain in `Feature_Catalog`.

## Useful read-only checks

```sql
SELECT status, count(*)
FROM public."Feature_Calculation_Queue"
GROUP BY status ORDER BY status;

SELECT ticker, latest_price_date, status, pending_count,
       processing_count, failed_count, last_error
FROM public."Feature_Status"
WHERE status <> 'SUCCESS'
ORDER BY updated_at DESC LIMIT 20;

SELECT ticker, price_date, attempt_no, result, rows_refreshed,
       started_at, finished_at, detail
FROM public."Feature_Calculation_Log"
ORDER BY id DESC LIMIT 20;
```

Run `python worker.py --once` only for a controlled diagnostic: it processes at most one claim (the due items of one ticker). It does not create a price candle or query TradingView.

## Tests

`test_worker_db.py` builds a scratch database from the real migrations (20260912_001 … 20260913_006 and the enqueue function of 20261025_011) on `FEATURE01_TEST_POSTGRES_URL`'s server and checks the coalesced claim against a from-scratch refresh, the single-item path, a re-ingestion during a claim and a failure.
