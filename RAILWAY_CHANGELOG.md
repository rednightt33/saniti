# Railway changelog

This file records intentional changes to the Railway project. Git history preserves every revision. Never include secret values.

## 2026-09-06

### GitHub tracking contract established

- Added mandatory AI read order and same-task GitHub update rules.
- Added separate database and Railway changelogs.
- Added forward-only SQL migrations for database schema history.
- Imported the current project as a secret-safe `.railway/railway.ts` snapshot.
- Extended the daily GitHub Action to capture Railway configuration drift and database schema changes.
- Kept live secrets and raw production data outside GitHub.

### PostgreSQL daily-price table

- Loaded 668,967 daily price rows into the PostgreSQL service in environment `dev`.
- Renamed the table to `Price_Stock_Indonesia_IDX` for the requested capitalization.
- No Railway service, deployment, domain, or environment-variable values changed.

### Broker-summary supervisor

- A local Windows supervisor was introduced for the Stockbit backfill.
- This is a process on the user's PC, not a Railway service or deployment.
- It resumes incomplete dates and recreates the temporary PostgreSQL TCP proxy after connection failure.

### Broker-summary authentication recovery

- Replaced the expired Stockbit session credential in the local Windows supervisor; no credential value was committed.
- Restarted the supervisor and preserved all dates already marked `COMPLETED`.
- Confirmed the existing Railway PostgreSQL TCP proxy and database connection remained healthy.
- Verified automatic recovery from the earliest `NEEDS_REVIEW` date before allowing the backfill to continue.
- No Railway service, deployment, domain, or environment-variable values changed.

### Automated IDX daily prices

- Created service `idx-price-cron` in environment `dev` (service ID `43c86c6f-3221-4403-83c3-cd3056441558`).
- Deployed the final Python/Docker TradingView price updater; verified deployment `ddd2ba96-d64e-414a-a5c7-87e15eeb23f8` reached `SUCCESS`.
- Connected `DATABASE_URL` to the existing Railway PostgreSQL service using a Railway variable reference; no credential value is stored in GitHub.
- Set cron schedule `0 10,23 * * *` UTC, corresponding to 17:00 Asia/Jakarta for the full `DAILY` run and 06:00 Asia/Jakarta the following day for missing-symbol `RECOVERY`.
- Set restart policy to `NEVER` so a failed recovery cannot create an unapproved third TradingView query.
- The first full TradingView query is scheduled for 2026-09-07 at 17:00 Asia/Jakarta. Existing price history through 2026-09-04 remains unchanged.
- Pulled the resulting live Railway state into `.railway/railway.ts`; the follow-up configuration plan reported no drift.

### Parallel historical broker-summary backfill

- Added a second local Windows supervisor for a descending, database-only backfill from 2025-08-31 through 2018-01-01.
- Kept the existing ascending backfill active and assigned separate status/log files to each process.
- Added a five-consecutive-401/403 stop rule to both supervisors so an invalid Stockbit token stops querying instead of marking the remaining date range `NEEDS_REVIEW`.
- Historical CSV export is disabled; only operational status and logs are retained locally.
- No Railway service, deployment, domain, or environment-variable values changed.
