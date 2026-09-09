# Railway changelog

This file records intentional changes to the Railway project. Git history preserves every revision. Never include secret values.

## 2026-09-09 — Telegram controls for manual IDX price runs

- Created public serverless service `telegram-trigger` (service ID `5a3f820c-2bb2-494b-b771-15fa6a5eb48a`, service-instance ID `78bd93d5-f74a-42fb-ad25-2be856bbda07`).
- Deployed the final webhook build as `3e8fd2fe-1cb6-47e7-9233-209bf259d404`; Railway reported `SUCCESS`, and `/health` returned `ok`.
- Registered `https://telegram-trigger-dev.up.railway.app/telegram/webhook` with Telegram for messages and button callbacks. Telegram reported zero pending updates and no webhook error; the bot command menu exposes `start`, `run_price`, and `run_recovery`.
- Added fixed controls for `idx-price-cron` and `idx-price-recovery-cron`. Only the configured owner Chat ID is accepted; arbitrary service names are never accepted from Telegram input.
- Stored the bot token, webhook secret, environment-scoped Railway project token, Chat ID, database reference, allowlisted service-instance IDs, and cooldown as Railway variables. No secret value is stored in Git.
- Added webhook-retry deduplication through `Telegram_Command_Log.telegram_update_id` and a 15-minute per-service rapid-click cooldown.
- Kept Telegram acknowledgement delivery independent from Railway acceptance so a temporary chat-message failure cannot relabel or repeat a successfully started cron job.
- Sent the `/start` menu successfully and ran one end-to-end RECOVERY test. The first command was accepted, an identical replay was ignored, execution `9926d137-6316-4c04-a1c2-099d87bd4735` completed for 2026-09-08, and `telegram-monitor` recorded the final message as `SENT`.
- The scheduled DAILY and RECOVERY start commands, 17:00/06:00 Asia/Jakarta schedules, exact candle-date rule, and existing completion-notification flow were not changed. No DAILY query was run during this deployment.
- Pulled the live Railway configuration into `.railway/railway.ts`; the follow-up plan reported no drift.

## 2026-09-09 — Correct Telegram private endpoint port

- Confirmed manual DAILY execution `1d50802c-caa7-4d1f-9d5d-055b0402eb4f` completed with 829 of 844 symbols but its Telegram request still failed.
- Root cause: both cron services had resolved `TELEGRAM_NOTIFY_URL` to `http://telegram-monitor.railway.internal:/notify` because the referenced service-level `PORT` variable was empty. The request therefore used the wrong port.
- Set both DAILY and RECOVERY notification URLs to the explicit private listener port `8080`; the resulting service deployments `db51a5fe-b845-44c3-abcc-5a91a3883bba` and `1c3e79af-19aa-4482-906a-bab7584c51c4` reached `SUCCESS` without querying TradingView.
- Re-sent the completed manual DAILY execution without running the price query. Telegram delivery was recorded as `SENT`; a repeat returned `duplicate`, confirming anti-duplicate handling.

## 2026-09-09 — Fix Telegram private-network wake and message spacing

- Diagnosed manual DAILY execution `c225b4c9-a009-4295-93f0-59ad4b6bb209`: TradingView processed 844 tickers in about six minutes and wrote 822 exact-date rows with 22 missing; Telegram added about nine seconds before failing with private-network `connection refused`.
- Changed only `telegram-monitor`: it now listens on Railway IPv6 private networking while preserving IPv4 compatibility where available.
- Added one blank line between the status summary and the `Missing:` ticker list.
- Notification calls remain active for both MANUAL and SCHEDULED executions of DAILY and RECOVERY. Query, worker, candle-date, and upsert behavior are unchanged.
- Deployed the fix as `282174bb-10e1-43e1-b498-f90b0742ff94`; Railway reported `SUCCESS` and `/health` returned HTTP 200.

## 2026-09-09 — Event-driven Telegram notifications for IDX price jobs

- Created the separate `telegram-monitor` service (service ID `a6b4e061-721f-4173-82f8-07ccb45740fc`) with no cron schedule, `/health` health check, `ALWAYS` restart policy, and Railway serverless sleep enabled.
- Stored the Telegram bot token, Chat ID, and shared caller secret only as Railway variables; no secret value is stored in GitHub or PostgreSQL.
- Configured `idx-price-cron` and `idx-price-recovery-cron` to send their committed `Monitoring_Price_ALL.execution_id` over Railway private networking. The caller retries temporary wake/network failures and does not roll back price data if notification delivery fails.
- Deployed `telegram-monitor` successfully as deployment `c4bf00cd-3452-4279-8342-ad21c55af9df`; Chat ID activation produced successful redeployment `19cc3f3c-c848-43fd-8fe4-5e9abd531551`, and the final shared-secret rotation produced successful deployment `6c4886fa-ebf4-45ba-b01c-1501c0a71974`.
- Deployed notification-enabled DAILY build `14ec1625-9b26-4f9f-9d53-7a3f63665266` and RECOVERY build `7a126d48-0a67-473c-a62c-004abf68a000`; both reached `SUCCESS` without executing TradingView.
- Sent one end-to-end test from historical RECOVERY execution `80d7d401-d1a2-4ac8-a276-dfbb4e89299b`. A second request returned `duplicate`, confirming the anti-duplicate ledger.
- Removed stale `valiant-connection` declarations from `.railway/railway.ts` because that service and volume are no longer present in the live `dev` environment; no live resource was deleted.

## 2026-09-09

### Correct recovery cron completion status

- Confirmed the scheduled recovery completed its database work in about two seconds, wrote 12 missing symbols as `NEEDS_REVIEW`, closed its PostgreSQL connection, and released its advisory lock.
- Corrected `NEEDS_REVIEW` to exit with code `0` because it is a completed, monitored business outcome rather than a crashed process.
- Kept a non-zero process exit exclusively for an actual `FAILED` status or an unhandled exception.
- Added regression tests for both reviewable and failed outcomes.
- Verified a no-database, no-TradingView Railway smoke execution (`7da53b07-351d-4682-93e2-9af2776e0700`) reached `EXITED` in about two seconds.
- Restored the production recovery start command and verified final RECOVERY deployment `9527e31d-fdd2-46bc-84c3-7ca29c486161` and DAILY deployment `b5d09e04-a255-4441-9dbe-dde0708b05a7` reached `SUCCESS`.

## 2026-09-08

### Guarantee IDX cron process termination

- Diagnosed `idx-price-recovery-cron` remaining `Active` after its 06:05 Asia/Jakarta work had already emitted `run_completed` and recorded 13 symbols as `NEEDS_REVIEW`.
- Added a guarded entrypoint that flushes stdout/stderr and explicitly terminates the process after database contexts close, including non-zero `NEEDS_REVIEW` and failure paths.
- Replaced the stuck recovery instance without issuing another TradingView query.
- Verified DAILY deployment `c831e1ed-0b76-42dc-9ac9-7006906832eb` and RECOVERY deployment `f751f9a1-c8d3-423a-9ccf-fd98d492d75c` reached `SUCCESS`.
- Verified both cron services returned to waiting state and recovery remains scheduled for 06:00 Asia/Jakarta.

## 2026-09-07

### Broker-summary authentication-stop repair

- Stopped both local historical supervisors after detecting repeated Stockbit HTTP 401 responses.
- Corrected the runner so authentication exhaustion reaches the supervisor as exit code 3 instead of being treated as an ordinary per-date failure.
- Replaced the Stockbit credential only in the new local process environments; its value was not persisted.
- Restarted both non-overlapping historical supervisors with three API workers each and verified successful recovery loads in both ranges.
- No Railway service, deployment, domain, or environment-variable values changed.

### Manual-safe IDX price services

- Changed `idx-price-cron` to explicit DAILY mode with schedule `0 10 * * *` UTC (17:00 Asia/Jakarta). Its **Run now** action performs a full current-day universe query.
- Created `idx-price-recovery-cron` (service ID `a8e6e32a-fcd8-4c33-9ecc-1488a4b2db05`) in environment `dev`, with explicit RECOVERY mode and schedule `0 23 * * *` UTC (06:00 Asia/Jakarta). Its **Run now** action retries only the preceding weekday's DAILY missing symbols; Saturday, Sunday, and Monday target Friday.
- Both services use the existing PostgreSQL variable reference, Dockerfile build, and `NEVER` restart policy.
- Added exact candle-date validation, `(ticker, date)` upsert protection, per-execution monitoring history, and a shared PostgreSQL advisory lock.
- No manual TradingView query was triggered during deployment.
- Verified final DAILY deployment `c9764e81-3b34-44b2-9402-c1fc212622f6` and final RECOVERY deployment `a8fc3609-2809-4bfa-b387-578631a8baa3` reached `SUCCESS`.
- Pulled the live configuration into `.railway/railway.ts`; the follow-up Railway configuration plan reported no drift.
- Triggered **Run now** on `idx-price-cron` after deployment. Execution `f4fd425d-edfe-433a-9925-99d052c794c5` ran in explicit DAILY mode, queried all 844 universe tickers, updated 824 exact-date candles, and correctly retained 20 no-current-candle symbols as missing with `PARTIAL` status.

### Historical broker-summary workers split

- Replaced the single local 2025-08-31 through 2018-01-01 supervisor with two concurrent, non-overlapping local supervisors.
- Recent range: 2025-08-31 through 2021-01-01 descending; older range: 2020-12-31 through 2018-01-01 descending.
- Set each process to three API workers so combined Stockbit concurrency remains six.
- Kept separate status and log paths, disabled local CSV output, and retained the five-consecutive-401/403 stop rule for both processes.
- Both supervisors use the existing Railway PostgreSQL TCP proxy. No Railway service, deployment, domain, or environment-variable values changed.

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
