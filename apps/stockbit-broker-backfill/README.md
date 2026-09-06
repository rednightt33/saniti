# Stockbit broker-summary backfill

This local Windows runner loads market-wide Stockbit broker activity into Railway PostgreSQL table `public."IDX_Broker_Summary"`. It is not deployed as a Railway service.

## Safety and resume behavior

- Dates recorded as `COMPLETED` in `stockbit_broker_summary_load_log` are skipped.
- Transient network, HTTP 429, and Stockbit 5xx failures are retried.
- Ordinary per-date failures are recorded as `NEEDS_REVIEW`, allowing later dates to continue.
- Five consecutive Stockbit HTTP 401/403 responses stop the query with `STOPPED_INVALID_TOKEN`. This prevents an expired token from marking the remaining date range for review.
- The supervisor recreates the temporary Railway PostgreSQL TCP proxy after a database-connection failure.
- Secrets are read only from `STOCKBIT_TOKEN` and `RAILWAY_TOKEN`; never place their values in Git.

## Current parallel runs

| Run | Direction | Inclusive range | Local CSV |
|---|---|---|---|
| Forward | Ascending | 2025-11-17 through 2026-08-31 | Enabled |
| Historical | Descending | 2025-08-31 through 2018-01-01 | Disabled |

Because 2025-08-31 is a Sunday, the historical run's first requested trading-day candidate is 2025-08-29. The historical run covers 2,000 weekdays. Both runs write to the same PostgreSQL table and use separate status/log paths.

## Files

- `stockbit_marketwide_broker_activity.py`: validates, fetches, loads, resumes, and optionally exports each date.
- `run_stockbit_backfill_background.ps1`: long-running local supervisor and Railway proxy recovery.
- `requirements.txt`: Python database dependency.

The runner accepts `--date-order descending` for reverse chronological processing and `--no-daily-export` for database-only loads. The supervisor exposes the equivalent `-DateOrder descending` and `-NoDailyExport` parameters.

After `STOPPED_INVALID_TOKEN`, obtain a new Stockbit JWT and restart the affected supervisor. Completed dates remain preserved in PostgreSQL and will be skipped during the restart.
