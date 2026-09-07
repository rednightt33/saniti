# Stockbit broker-summary backfill

This local Windows runner loads market-wide Stockbit broker activity into Railway PostgreSQL table `public."IDX_Broker_Summary"`. It is not deployed as a Railway service.

## Safety and resume behavior

- Dates recorded as `COMPLETED` in `stockbit_broker_summary_load_log` are skipped.
- Transient network, HTTP 429, and Stockbit 5xx failures are retried.
- Ordinary per-date failures are recorded as `NEEDS_REVIEW`, allowing later dates to continue.
- Five consecutive Stockbit HTTP 401/403 responses bypass date-level retries and stop the query with `STOPPED_INVALID_TOKEN`. This prevents an expired token from marking the remaining date range for review.
- The supervisor recreates the temporary Railway PostgreSQL TCP proxy after a database-connection failure.
- Secrets are read only from `STOCKBIT_TOKEN` and `RAILWAY_TOKEN`; never place their values in Git.

## Current runs

| Run | Direction | Inclusive range | Local CSV |
|---|---|---|---|
| Forward (complete) | Ascending | 2025-11-17 through 2026-08-31 | Enabled |
| Historical recent | Descending | 2025-08-31 through 2021-01-01 | Disabled |
| Historical older | Descending | 2020-12-31 through 2018-01-01 | Disabled |

Because 2025-08-31 is a Sunday, the recent historical run's first requested trading-day candidate is 2025-08-29. The recent and older historical ranges contain 1,216 and 784 weekdays respectively. They run concurrently with three API workers each, write to the same PostgreSQL table, and use separate status/log paths. This keeps total API concurrency at six while avoiding date overlap.

## Files

- `stockbit_marketwide_broker_activity.py`: validates, fetches, loads, resumes, and optionally exports each date.
- `test_stockbit_marketwide_broker_activity.py`: regression test proving authentication exhaustion stops the process without writing `NEEDS_REVIEW`.
- `run_stockbit_backfill_background.ps1`: long-running local supervisor and Railway proxy recovery.
- `requirements.txt`: Python database dependency.

The runner accepts `--date-order descending` for reverse chronological processing and `--no-daily-export` for database-only loads. The supervisor exposes the equivalent `-DateOrder descending` and `-NoDailyExport` parameters.

After `STOPPED_INVALID_TOKEN`, obtain a new Stockbit JWT and restart the affected supervisor. Completed dates remain preserved in PostgreSQL and will be skipped during the restart.
